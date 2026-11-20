import type { Linter, Rule } from 'eslint';

export declare const noRawColorStrings: Rule.RuleModule;
export declare const noArbitraryColorLiterals: Rule.RuleModule;
export declare const dedupeRawColors: Linter.Processor & {
  postprocess: (messages: Linter.LintMessage[][]) => Linter.LintMessage[];
};
