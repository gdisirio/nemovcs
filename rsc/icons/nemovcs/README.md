# Temporary Icon Assets

Most icons in this directory are temporary development assets derived from
RabbitVCS icon assets.

The app icons under `apps/` are NemoVCS-native artwork and are not derived from
RabbitVCS.

The `nemovcs-git` action icon is a Wikimedia Git logo asset under Creative
Commons Attribution 3.0 Unported. The `nemovcs-svn` action icon is a Wikimedia
Subversion logo asset under Creative Commons Attribution-ShareAlike 3.0
Unported, normalized to a square viewBox for menu use.

The default `normal`, `modified`, and `conflicted` emblems use a cropped
`viewBox` so Nemo renders the overlay artwork larger. The `*-small.svg`
variants keep the original full canvas for a future size/style setting.

Observed source license:

```text
GPL-2.0
```

NemoVCS is currently licensed as `GPL-2.0-or-later`, so these assets are likely
compatible, but they should be treated as imported third-party assets until the
icon licensing/provenance is reviewed more carefully.

Replacement direction:

- create NemoVCS-native icons,
- use system theme icons where possible,
- or keep only clearly licensed upstream assets with explicit attribution.
