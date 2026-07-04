# skills/

Drop `SKILL.md`-based skills here. The pydantic-deepagents harness auto-discovers
this directory and loads skills on demand (progressive disclosure — only a skill's
short description is always in context; the body loads when relevant).

Layout for a skill:

```
skills/
  my-skill/
    SKILL.md          # required: name + description frontmatter, then instructions
    scripts/          # optional executables the skill calls
    references/       # optional reference docs loaded on demand
```

Empty for now (Phase 1–2). We'll add skills in Phase 4 when the evaluator-optimizer
pair starts generating the five general-purpose agents — recurring workflows that
show up across agents become skills.
