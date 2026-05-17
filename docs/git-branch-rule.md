<!-- docs/git-branch-rule.md -->

This document explains the Git branch naming rules for the project.

```ebnf
(* branch name is either planned work or community ticket *)
git-branch-name = topic | ticket ;

(* planned work: type / scope-desc *)
topic = type, "/", [ scope, "-" ], desc ;
type = "feature" | "hotfix" | "perf" ;
scope = identifier ;
desc = identifier, { "-", identifier } ;

(* community ticket: issue or discussion / number *)
ticket = ("issue" | "discussion"), "/", number ;
number = ? regex:/[1-9][0-9]*/ ? ;

(* branch name base info *)
identifier = ? regex:/[A-Za-z][A-Za-z0-9]*/ ? ;
```

The rules above define all valid branch names for this repository.

---
