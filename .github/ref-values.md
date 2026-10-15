# `ref` values for links to digline.dev

The closed set of values a link to digline.dev may carry as `?ref=`. One value
per channel, lowercase, with no variants and no synonyms.

**This list is not modified.** It was fixed on 2026-10-15, before the baseline
window opened, because the value of `ref` is the only direct attribution a
visit has; a value added, renamed or merged later would split one channel's
count in two, or join two channels in one. The same reason works the other way:
a channel left out now could never be counted. So `pypi`, `email` and `podcast`
were added on 2026-10-15 to the eight values first proposed, before the list
was closed: a value that is never used costs nothing, and one that is missing
cannot be added.

| Value | Channel |
|---|---|
| `reddit` | Reddit |
| `hn` | Hacker News |
| `linkedin` | LinkedIn |
| `slack` | Slack |
| `discord` | Discord |
| `newsletter` | a newsletter |
| `github` | GitHub |
| `x` | X |
| `pypi` | PyPI, from a package's project page |
| `email` | an email, cold contact included |
| `podcast` | a podcast |

A visit that arrives without `ref` is counted as without `ref`. Where it came
from is not guessed.
