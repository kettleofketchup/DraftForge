// DraftForge design-system rules for people: avatars go through UserAvatar, names
// through DisplayName (which picks org server nickname, Discord name or username).

const GUIDE = '.claude/skills/frontend-development/resources/users.md';
const see = (rule) => ` See ${GUIDE}#${rule}`;

const NAME_FIELDS = new Set([
  'username',
  'nickname',
  'discordNickname',
  'guildNickname',
  'discordUsername',
  'global_name',
]);
// Attributes a person reads; ids, keys, test ids and links keep the raw username.
const NAME_ATTRIBUTES = new Set([
  'title',
  'alt',
  'aria-label',
  'placeholder',
  'label',
]);
const LOG_OBJECTS = new Set(['log', 'logger', 'console']);
const RESOLVERS = new Set(['resolveDisplayName', 'AvatarUrl']);
const ID_ALIASES = new Set(['user_id', 'user', 'id']);

function propertyName(node) {
  if (node?.type !== 'MemberExpression') return null;
  if (!node.computed && node.property.type === 'Identifier')
    return node.property.name;
  if (node.computed && node.property.type === 'Literal')
    return String(node.property.value);
  return null;
}

function unwrap(node) {
  let n = node;
  while (
    n &&
    (n.type === 'ChainExpression' ||
      n.type === 'TSNonNullExpression' ||
      n.type === 'TSAsExpression')
  ) {
    n = n.expression;
  }
  return n;
}

// Members whose value ends up rendered: the expression itself, || / ?? operands,
// the right side of &&, ternary branches (not the test), template-literal parts
// and string concatenation.
function renderedMembers(node, out = []) {
  const n = unwrap(node);
  if (!n) return out;
  if (n.type === 'MemberExpression') out.push(n);
  else if (n.type === 'LogicalExpression' && n.operator !== '&&') {
    renderedMembers(n.left, out);
    renderedMembers(n.right, out);
  } else if (n.type === 'LogicalExpression') renderedMembers(n.right, out);
  else if (n.type === 'ConditionalExpression') {
    renderedMembers(n.consequent, out);
    renderedMembers(n.alternate, out);
  } else if (n.type === 'TemplateLiteral')
    n.expressions.forEach((e) => renderedMembers(e, out));
  else if (n.type === 'BinaryExpression' && n.operator === '+') {
    renderedMembers(n.left, out);
    renderedMembers(n.right, out);
  }
  return out;
}

function jsxName(node) {
  const n = node.name;
  if (n.type === 'JSXIdentifier') return n.name;
  if (n.type === 'JSXMemberExpression') return n.property.name;
  return null;
}

function attributeName(node) {
  const n = node.name;
  if (n.type === 'JSXIdentifier') return n.name;
  if (n.type === 'JSXNamespacedName')
    return `${n.namespace.name}:${n.name.name}`;
  return null;
}

function ownerText(sourceCode, member) {
  const obj = unwrap(member.object);
  return obj ? sourceCode.getText(obj) : '';
}

// Strings not shown to a person (logger calls, query keys) or handled by the JSX
// paths (children, attributes). A function boundary ends the search: a handler
// body's strings are its own, whatever attribute holds the handler.
function isQuietContext(node) {
  for (let p = node.parent, child = node; p; child = p, p = p.parent) {
    if (
      p.type === 'ArrowFunctionExpression' ||
      p.type === 'FunctionExpression' ||
      p.type === 'FunctionDeclaration'
    )
      return false;
    if (p.type === 'CallExpression' && child !== p.callee) {
      const callee = unwrap(p.callee);
      if (
        callee?.type === 'MemberExpression' &&
        callee.object.type === 'Identifier' &&
        LOG_OBJECTS.has(callee.object.name)
      )
        return true;
    }
    if (p.type === 'JSXAttribute') return true;
    if (
      p.type === 'JSXExpressionContainer' &&
      (p.parent?.type === 'JSXElement' || p.parent?.type === 'JSXFragment')
    )
      return true;
    if (
      p.type === 'Property' &&
      child === p.value &&
      !p.computed &&
      p.key.type === 'Identifier' &&
      /key$/i.test(p.key.name)
    )
      return true;
    if (
      p.type === 'ArrayExpression' &&
      p.parent?.type === 'Property' &&
      p.parent.key.type === 'Identifier' &&
      /key$/i.test(p.parent.key.name)
    )
      return true;
    if (p.type === 'TaggedTemplateExpression') return true;
  }
  return false;
}

const useDisplayName = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Render person names through DisplayName',
      url: `${GUIDE}#use-display-name`,
    },
    messages: {
      raw:
        'Person name `.{{field}}` rendered directly; use DisplayName(user) so org server nicknames and Discord names apply.' +
        see('use-display-name'),
    },
    schema: [],
  },
  create(context) {
    const report = (members) => {
      for (const member of members) {
        const field = propertyName(member);
        if (NAME_FIELDS.has(field))
          context.report({ node: member, messageId: 'raw', data: { field } });
      }
    };
    const outermost = (node) =>
      node.parent?.type === 'TemplateLiteral' ||
      (node.parent?.type === 'BinaryExpression' &&
        node.parent.operator === '+');
    return {
      JSXExpressionContainer(node) {
        const parent = node.parent;
        if (parent?.type === 'JSXElement' || parent?.type === 'JSXFragment') {
          report(renderedMembers(node.expression));
        } else if (
          parent?.type === 'JSXAttribute' &&
          NAME_ATTRIBUTES.has(attributeName(parent) ?? '')
        ) {
          report(renderedMembers(node.expression));
        }
      },
      'TemplateLiteral, BinaryExpression'(node) {
        if (node.type === 'BinaryExpression' && node.operator !== '+') return;
        if (outermost(node) || isQuietContext(node)) return;
        if (
          node.type === 'BinaryExpression' &&
          ![node.left, node.right].some(
            (s) =>
              (s.type === 'Literal' && typeof s.value === 'string') ||
              s.type === 'TemplateLiteral',
          )
        )
          return;
        report(renderedMembers(node));
      },
    };
  },
};

const useUserAvatar = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Render user avatars through UserAvatar',
      url: `${GUIDE}#use-user-avatar`,
    },
    messages: {
      raw:
        'User avatar rendered with raw <AvatarImage>; use <UserAvatar user={...} /> for the shared fallback, sizes and Discord URL handling.' +
        see('use-user-avatar'),
    },
    schema: [],
  },
  create(context) {
    return {
      JSXOpeningElement(node) {
        if (jsxName(node) !== 'AvatarImage') return;
        const src = node.attributes.find(
          (a) => a.type === 'JSXAttribute' && a.name.name === 'src',
        );
        const value = src?.value;
        if (
          value?.type === 'JSXExpressionContainer' &&
          readsMatching(value.expression, PERSON_AVATAR, /^(avatar|avatarUrl)$/)
        ) {
          context.report({ node, messageId: 'raw' });
        }
      },
    };
  },
};

const noDisplayOrgArg = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Let DisplayName derive the org from the route',
      url: `${GUIDE}#no-display-org-arg`,
    },
    messages: {
      explicit:
        'DisplayName derives the org from the current page; drop the org argument. For a deliberate override, disable this line with a reason.' +
        see('no-display-org-arg'),
    },
    schema: [],
  },
  create(context) {
    return {
      CallExpression(node) {
        const callee = unwrap(node.callee);
        if (
          callee?.type === 'Identifier' &&
          callee.name === 'DisplayName' &&
          node.arguments.length >= 3
        )
          context.report({ node: node.arguments[2], messageId: 'explicit' });
      },
    };
  },
};

const noUserReshape = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Pass the user payload to UserAvatar as-is',
      url: `${GUIDE}#no-user-reshape`,
    },
    messages: {
      reshape:
        'UserAvatar resolves {{root}} by pk / user_id and fills the rest from the user cache; pass user={{{root}}} instead of copying its fields.' +
        see('no-user-reshape'),
    },
    schema: [],
  },
  create(context) {
    const sourceCode = context.sourceCode ?? context.getSourceCode();
    return {
      JSXOpeningElement(node) {
        if (jsxName(node) !== 'UserAvatar') return;
        const attr = node.attributes.find(
          (a) => a.type === 'JSXAttribute' && a.name.name === 'user',
        );
        const obj = attr?.value?.expression;
        if (obj?.type !== 'ObjectExpression' || obj.properties.length === 0)
          return;
        // Only copies count: each key reads the same-named field (or pk from an id alias).
        const roots = new Set();
        for (const prop of obj.properties) {
          if (prop.type !== 'Property' || prop.computed) return;
          let value = unwrap(prop.value);
          if (value?.type === 'LogicalExpression') value = unwrap(value.left);
          if (value?.type !== 'MemberExpression') return;
          const key = prop.key.type === 'Identifier' ? prop.key.name : null;
          const field = propertyName(value);
          if (key !== field && !(key === 'pk' && ID_ALIASES.has(field))) return;
          roots.add(ownerText(sourceCode, value));
        }
        if (roots.size === 1)
          context.report({
            node: attr,
            messageId: 'reshape',
            data: { root: [...roots][0] },
          });
      },
    };
  },
};

const noDirectNameResolver = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Use DisplayName / UserAvatar, not the resolvers',
      url: `${GUIDE}#no-direct-name-resolver`,
    },
    messages: {
      direct:
        '{{name}} is internal to the name and avatar helpers; use DisplayName(user) or <UserAvatar user={...} />.' +
        see('no-direct-name-resolver'),
    },
    schema: [],
  },
  create(context) {
    return {
      CallExpression(node) {
        const callee = unwrap(node.callee);
        if (callee?.type === 'Identifier' && RESOLVERS.has(callee.name))
          context.report({
            node: callee,
            messageId: 'direct',
            data: { name: callee.name },
          });
      },
    };
  },
};

const PERSON_NAME =
  /(^|_)(username|nickname|discordnickname|guildnickname|global_name)$/i;
const PERSON_NAME_VAR = /^(displayName|username|nickname)$/;
const PERSON_AVATAR = /(^|_)avatar(url)?$/i;

// Reads a member whose name matches `pattern`, or a bare identifier matching `bareIdentifiers`.
function readsMatching(node, pattern, bareIdentifiers) {
  let found = false;
  const visit = (n) => {
    if (!n || found || typeof n.type !== 'string') return;
    const prop = propertyName(n);
    if (prop && pattern.test(prop)) {
      found = true;
      return;
    }
    if (n.type === 'Identifier' && bareIdentifiers.test(n.name)) {
      const parent = n.parent;
      const isProperty =
        parent?.type === 'MemberExpression' &&
        parent.property === n &&
        !parent.computed;
      if (!isProperty) {
        found = true;
        return;
      }
    }
    for (const key of Object.keys(n)) {
      if (key === 'parent') continue;
      const v = n[key];
      if (Array.isArray(v)) v.forEach(visit);
      else if (v && typeof v.type === 'string') visit(v);
    }
  };
  visit(node);
  return found;
}

function elementName(node) {
  return node?.type === 'JSXElement' ? jsxName(node.openingElement) : null;
}

function callsDisplayName(node) {
  let found = false;
  const visit = (n) => {
    if (!n || found || typeof n.type !== 'string') return;
    if (
      n.type === 'CallExpression' &&
      unwrap(n.callee)?.type === 'Identifier' &&
      unwrap(n.callee).name === 'DisplayName'
    ) {
      found = true;
      return;
    }
    for (const key of Object.keys(n)) {
      if (key === 'parent') continue;
      const v = n[key];
      if (Array.isArray(v)) v.forEach(visit);
      else if (v && typeof v.type === 'string') visit(v);
    }
  };
  visit(node);
  return found;
}

const noAvatarFallback = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Let UserAvatar render the no-user fallback',
      url: `${GUIDE}#no-avatar-fallback`,
    },
    messages: {
      branch:
        'UserAvatar renders the fallback when there is no user; use one <UserAvatar user={...} fallbackName={...} /> instead of a raw <Avatar> branch.' +
        see('no-avatar-fallback'),
      initials:
        'Person initials in <AvatarFallback>; use <UserAvatar user={...} />, which derives them from the display name.' +
        see('no-avatar-fallback'),
    },
    schema: [],
  },
  create(context) {
    return {
      ConditionalExpression(node) {
        const a = unwrap(node.consequent);
        const b = unwrap(node.alternate);
        for (const [mine, other] of [
          [a, b],
          [b, a],
        ]) {
          if (
            elementName(mine) === 'Avatar' &&
            elementName(other) === 'UserAvatar'
          )
            context.report({ node: mine, messageId: 'branch' });
        }
      },
      JSXElement(node) {
        if (elementName(node) !== 'AvatarFallback') return;
        const personal = (n) =>
          readsMatching(n, PERSON_NAME, PERSON_NAME_VAR) || callsDisplayName(n);
        if (node.children.some(personal))
          context.report({ node, messageId: 'initials' });
      },
    };
  },
};

export default {
  meta: { name: 'draftforge' },
  rules: {
    'use-display-name': useDisplayName,
    'use-user-avatar': useUserAvatar,
    'no-display-org-arg': noDisplayOrgArg,
    'no-user-reshape': noUserReshape,
    'no-direct-name-resolver': noDirectNameResolver,
    'no-avatar-fallback': noAvatarFallback,
  },
};
