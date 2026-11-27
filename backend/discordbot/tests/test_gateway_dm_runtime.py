"""Runtime backstop for the DM guard: drive every gateway component and modal.

``discord.abc.Messageable.send`` and ``HTTPClient.start_private_message`` are
patched, every ``ui.Modal``/``ui.View``/``ui.Button``/``ui.Select`` subclass
under ``discordbot`` is driven with a fake interaction across canned backend
results, and every DM-channel send must happen inside ``send_interaction_dm``.
"""

import ast
import inspect
import itertools
import pkgutil
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord import ui
from django.conf import settings

from discordbot import components, gateway_dm, interaction_router
from discordbot.custom_ids import (
    DeclineId,
    NotifyId,
    PosSelectId,
    SignupId,
    TentativeId,
)
from discordbot.dm_ledger import ClaimResult
from discordbot.models import DMStatus

USER_ID = 4242
DM_CHANNEL_ID = 9100
UI_BASES: tuple[type, ...] = (ui.Modal, ui.View, ui.Button, ui.Select)
BASE_CALLBACKS: frozenset[object] = frozenset(
    {ui.Item.callback, ui.Button.callback, ui.Select.callback}
)
CTOR_ARGS: dict[str, object] = {
    "event_id": 1,
    "rank_status": "active",
    "screenshot_type": "rank",
}
ROUTER_IDS: tuple[str, ...] = (
    SignupId(event_id=1).encode(),
    TentativeId(event_id=1).encode(),
    DeclineId(event_id=1).encode(),
    NotifyId(event_id=1).encode(),
    PosSelectId(event_id=1, slot=1).encode(),
    "draft_activity:launch",
    "draft_activity:1:2",
)
GRANTED = ClaimResult(
    id=7, granted=True, status=DMStatus.PENDING, attempts=1, created=True
)


@dataclass
class Recorder:
    dm_sends: list[bool] = field(default_factory=list)
    other_sends: list[str] = field(default_factory=list)
    dm_opens: list[bool] = field(default_factory=list)
    driven: set[type] = field(default_factory=set)

    async def send(
        self, target: discord.abc.Messageable, *a: Any, **k: Any
    ) -> MagicMock:
        if isinstance(target, discord.DMChannel | discord.abc.User):
            self.dm_sends.append(gateway_dm._IN_GATEWAY_DM.get())
        else:
            self.other_sends.append(type(target).__name__)
        return MagicMock(id=8800)

    async def open_dm(
        self, http: discord.http.HTTPClient, user_id: int
    ) -> dict[str, Any]:
        self.dm_opens.append(gateway_dm._IN_GATEWAY_DM.get())
        return {"id": str(DM_CHANNEL_ID), "type": 1, "recipients": []}


class _FakeState:
    def __init__(self) -> None:
        self.http = object.__new__(discord.http.HTTPClient)
        self.user: discord.User | None = None

    def _get_private_channel_by_user(self, user_id: int) -> None:
        return None

    def store_user(self, data: dict[str, Any]) -> discord.User | None:
        return self.user

    def add_dm_channel(self, data: dict[str, Any]) -> discord.DMChannel:
        return discord.DMChannel(me=MagicMock(), state=self, data=data)  # type: ignore[arg-type]


class _ScenarioResult(dict[str, Any]):
    def __init__(self, value: str, flag: bool) -> None:
        super().__init__(
            action=value,
            status=value,
            success=flag,
            signed_up=flag,
            subscribed=flag,
            message="m",
        )
        self._value = value

    def __missing__(self, key: str) -> str:
        return self._value


def _interaction(custom_id: str = "") -> MagicMock:
    state = _FakeState()
    user = discord.User(
        state=state,  # type: ignore[arg-type]
        data={
            "id": str(USER_ID),
            "username": "rater",
            "discriminator": "0",
            "avatar": None,
        },
    )
    state.user = user
    interaction = MagicMock()
    interaction.id = 123456
    interaction.user = user
    interaction.guild_id = None
    interaction.guild = None
    interaction.channel_id = 55
    interaction.message = MagicMock(id=66)
    interaction.data = {"custom_id": custom_id, "values": ["1"], "resolved": {}}
    interaction.type = discord.InteractionType.component
    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=False)
    for name in (
        "defer",
        "send_message",
        "edit_message",
        "send_modal",
        "launch_activity",
    ):
        setattr(interaction.response, name, AsyncMock())
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    return interaction


def _discordbot_modules() -> list[ModuleType]:
    found = [components, interaction_router]
    found.extend(
        import_module(info.name)
        for info in pkgutil.walk_packages(
            components.__path__, f"{components.__name__}."
        )
    )
    return found


def _subclasses(cls: type) -> Iterator[type]:
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


def collected_classes() -> list[type]:
    _discordbot_modules()
    classes = {
        sub
        for base in UI_BASES
        for sub in _subclasses(base)
        if sub.__module__.startswith("discordbot.") and ".tests" not in sub.__module__
    }
    return sorted(classes, key=lambda c: (c.__module__, c.__qualname__))


def _declared_ui_classes() -> set[tuple[str, str]]:
    base: Path = settings.BASE_DIR_PATH
    found: set[tuple[str, str]] = set()
    for path in (base / "discordbot").rglob("*.py"):
        rel = path.relative_to(base)
        if {"tests", "migrations"} & set(rel.parts):
            continue
        module = ".".join(rel.with_suffix("").parts)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef) and any(
                ast.unparse(b).endswith(("Modal", "View", "Button", "Select"))
                for b in node.bases
            ):
                found.add((module, node.name))
    return found


def _scenario_values() -> list[str]:
    values: set[str] = set()
    for module in _discordbot_modules():
        for node in ast.walk(ast.parse(inspect.getsource(module))):
            if isinstance(node, ast.Compare):
                for part in (node.left, *node.comparators):
                    for const in ast.walk(part):
                        if isinstance(const, ast.Constant) and isinstance(
                            const.value, str
                        ):
                            values.add(const.value)
    return sorted(values)


def _build(cls: type) -> Any:
    kwargs: dict[str, object] = {}
    for name, param in inspect.signature(cls.__init__).parameters.items():
        if name == "self" or param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if name in CTOR_ARGS:
            kwargs[name] = CTOR_ARGS[name]
        elif param.default is inspect.Parameter.empty:
            raise AssertionError(f"{cls.__qualname__}: add {name!r} to CTOR_ARGS")
    return cls(**kwargs)


def _prime_select(item: object) -> None:
    if isinstance(item, ui.Select) and item.options:
        item._values = [item.options[0].value]


class GatewayDMRuntimeTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.rec = Recorder()
        self.result: _ScenarioResult = _ScenarioResult("", True)
        stack = ExitStack()
        self.addCleanup(stack.close)
        rec = self.rec
        stack.enter_context(
            patch.object(
                discord.abc.Messageable,
                "send",
                new=lambda s, *a, **k: rec.send(s, *a, **k),
            )
        )
        stack.enter_context(
            patch.object(
                discord.http.HTTPClient,
                "start_private_message",
                new=lambda s, uid: rec.open_dm(s, uid),
            )
        )
        stack.enter_context(patch.object(gateway_dm, "claim_dm", return_value=GRANTED))
        stack.enter_context(
            patch.object(gateway_dm, "mark_dm_sending", return_value=True)
        )
        stack.enter_context(patch.object(gateway_dm, "finalize_dm", return_value=True))
        stack.enter_context(
            patch.object(interaction_router, "handle_draft_launch", AsyncMock())
        )
        for module in _discordbot_modules():
            for name, value in vars(module).items():
                if name == "send_modal_v2":
                    stack.enter_context(patch.object(module, name, AsyncMock()))
                elif callable(value) and getattr(value, "__module__", "").startswith(
                    "discordbot.internal_client"
                ):
                    stack.enter_context(
                        patch.object(module, name, side_effect=self._backend_result)
                    )

    def _backend_result(self, *args: Any, **kwargs: Any) -> _ScenarioResult:
        return self.result

    async def _scenarios(self, run: Callable[[MagicMock], Any]) -> None:
        for value, flag in itertools.product(_scenario_values(), (True, False)):
            self.result = _ScenarioResult(value, flag)
            try:
                await run(_interaction(value))
            except Exception:  # noqa: BLE001 - only DM routing is under test
                pass

    async def _drive_item(self, item: ui.Item[Any]) -> None:
        if type(item).callback in BASE_CALLBACKS:
            return
        self.rec.driven.add(type(item))
        _prime_select(item)

        async def run(interaction: MagicMock) -> None:
            await item.callback(interaction)

        await self._scenarios(run)

    async def _drive_all(self) -> None:
        classes = collected_classes()
        for cls in classes:
            if issubclass(cls, ui.Modal):
                self.rec.driven.add(cls)

                async def submit(interaction: MagicMock, cls: type = cls) -> None:
                    await _build(cls).on_submit(interaction)

                await self._scenarios(submit)
            elif issubclass(cls, ui.View):
                self.rec.driven.add(cls)
                for child in _build(cls).children:
                    await self._drive_item(child)
        for cls in classes:
            if issubclass(cls, ui.Button | ui.Select) and cls not in self.rec.driven:
                await self._drive_item(_build(cls))
        for custom_id in ROUTER_IDS:

            async def route(interaction: MagicMock, custom_id: str = custom_id) -> None:
                interaction.data["custom_id"] = custom_id
                await interaction_router.route_component_interaction(
                    interaction, custom_id
                )

            await self._scenarios(route)

    async def test_every_dm_send_goes_through_send_interaction_dm(self) -> None:
        await self._drive_all()
        self.assertTrue(
            self.rec.dm_sends, "no component reached a DM; backstop is vacuous"
        )
        self.assertTrue(
            all(self.rec.dm_sends), "a DM was sent outside send_interaction_dm"
        )
        self.assertTrue(
            all(self.rec.dm_opens),
            "a DM channel was opened outside send_interaction_dm",
        )
        self.assertEqual(self.rec.other_sends, [])

    async def test_every_modal_is_driven(self) -> None:
        await self._drive_all()
        classes = collected_classes()
        modals = {c for c in classes if issubclass(c, ui.Modal)}
        self.assertGreaterEqual(len(modals), 4)
        self.assertEqual(modals - self.rec.driven, set())
        undriven = {
            c
            for c in classes
            if c not in self.rec.driven
            and not (
                issubclass(c, ui.Button | ui.Select) and c.callback in BASE_CALLBACKS
            )
        }
        self.assertEqual(undriven, set())

    async def test_every_declared_ui_class_is_collected(self) -> None:
        collected = {(c.__module__, c.__name__) for c in collected_classes()}
        self.assertEqual(_declared_ui_classes() - collected, set())

    async def test_backstop_flags_direct_user_send(self) -> None:
        await _interaction().user.send("hi")
        self.assertEqual(self.rec.dm_sends, [False])

    async def test_backstop_flags_direct_create_dm(self) -> None:
        channel = await _interaction().user.create_dm()
        await channel.send("hi")
        self.assertEqual(self.rec.dm_opens, [False])
        self.assertEqual(self.rec.dm_sends, [False])
