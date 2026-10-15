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

*2026-10-15: the parameter stays `ref`.* The eleven values are sources, and
`ref` is the parameter GoatCounter reads as a visit's source; `campaign` names
a campaign, which this list is not. Both produce a row: `ref` as the visit's
source, `campaign` as a name in the Campaigns panel. That was read in
`hit.go` on the `master` branch of arp242/goatcounter and in its *Track
campaigns* help page, not in the version goatcounter.com runs, and no real
count was tested. And the parameter is not changed because links already
published carry it: changing it now would split their attribution from that
of the links that follow.

*2026-10-15: what `github` and `pypi` can mean.* Every package in this
repository names `readme = "README.md"` in its `pyproject.toml`, so each
package's README is also its page on PyPI, and the README at the root is
digline's. A link inside a README cannot tell the two places apart: on such a
link, `github` means "the README", not "from GitHub". The *Project links* on a
PyPI page come instead from `[project.urls]`, not from the README. For every
package here they are Homepage, Documentation and Changelog, all to
digline.dev, and they appear only on PyPI, so `pypi` can be carried today, on
those links. None of them carries a `ref` yet; tagging them changes
`pyproject.toml` and is a decision not taken here.
