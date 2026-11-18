// DraftForge design-system rules for people: avatars go through UserAvatar, names
// through DisplayName (which picks org server nickname, Discord name or username).

const NAME_FIELDS = new Set([
  'username',
  'nickname',
  'discordNickname',
  'guildNickname',
  'discordUsername',
  'global_name',
]);
const AVATAR_FIELDS = new Set(['avatar', 'avatarUrl']);

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
// ternary branches (not the test) and template-literal parts.
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
  return out;
}

// Any member read inside an expression (for avatar src, which is often a template URL).
function readsField(node, fields) {
  let found = false;
  const visit = (n) => {
    if (!n || found || typeof n.type !== 'string') return;
    if (fields.has(propertyName(n))) {
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

function jsxName(node) {
  const n = node.name;
  if (n.type === 'JSXIdentifier') return n.name;
  if (n.type === 'JSXMemberExpression') return n.property.name;
  return null;
}

const useDisplayName = {
  meta: {
    type: 'problem',
    docs: { description: 'Render person names through DisplayName' },
    messages: {
      raw: 'Person name `.{{field}}` rendered directly; use DisplayName(user) so org server nicknames and Discord names apply.',
    },
    schema: [],
  },
  create(context) {
    return {
      JSXExpressionContainer(node) {
        const parent = node.parent;
        if (parent?.type !== 'JSXElement' && parent?.type !== 'JSXFragment')
          return;
        for (const member of renderedMembers(node.expression)) {
          const field = propertyName(member);
          if (NAME_FIELDS.has(field))
            context.report({ node: member, messageId: 'raw', data: { field } });
        }
      },
    };
  },
};

const useUserAvatar = {
  meta: {
    type: 'problem',
    docs: { description: 'Render user avatars through UserAvatar' },
    messages: {
      raw: 'User avatar rendered with raw <AvatarImage>; use <UserAvatar user={...} /> for the shared fallback, sizes and Discord URL handling.',
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
          readsField(value.expression, AVATAR_FIELDS)
        ) {
          context.report({ node, messageId: 'raw' });
        }
      },
    };
  },
};

export default {
  meta: { name: 'draftforge' },
  rules: {
    'use-display-name': useDisplayName,
    'use-user-avatar': useUserAvatar,
  },
};
