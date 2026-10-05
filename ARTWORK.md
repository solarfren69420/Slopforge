# Original Slopforge artwork

The two local user-supplied mockups were layout and palette references. Their fictional titles, commercial logos, and score claims are not copied into the published catalog. The original reference files are not redistributed.

## Forge illustration

- Tool: built-in `image_gen` through the imagegen skill.
- Generated on: 2026-10-05.
- Website asset: [`web/assets/forge-hero.webp`](web/assets/forge-hero.webp).
- Composition: a dark left field for live HTML text; an original robot and violet crystal forge on the right.
- Use: original atmospheric branding, not a screenshot or depiction of a listed game.

Final prompt:

> Use case: stylized-concept. Asset type: wide hero background artwork for Slopforge, a dark blue and purple storefront of community game engines and open-source creative tools. Create an original cinematic panoramic illustration, 3:1 landscape, no text, no words, no logos, no recognizable copyrighted characters or software icons. A futuristic forge/workshop suspended above a midnight alien canyon: on the RIGHT half a luminous faceted violet energy crystal floats over a circular brushed metal forge platform, surrounded by translucent cyan wireframe cubes, orbiting paths and tiny holographic workstation panels. A small original white-and-navy workshop robot tends the forge. Beyond it, floating islands, distant angular towers and a blue-violet nebula. Moody detailed painterly 3D concept art, high-end game storefront illustration. Electric blue, teal, purple, touches of amber sparks. Strong interesting silhouette and rich details on the RIGHT half. The LEFT 45 percent is dark navy atmosphere and gently lit canyon silhouettes, calm negative space to put HTML headings over. Bright subjects should not be on the far left. No UI frame or baked-in interface, no captions, no watermark. This is mood illustration, not a depiction of any cataloged game.

The source raster was preserved in the generation output directory. The website uses a compressed WebP copy. The README and share card use [`web/assets/social-preview.jpg`](web/assets/social-preview.jpg), rendered from the site's original HTML branding and forge art with [`scripts/render_brand.cjs`](scripts/render_brand.cjs).

## Card illustrations and logo

The SVG forge icon is original website artwork. Each project card contains a symbolic SVG diagram, landscape, or geometric illustration and a text monogram. Card illustrations are generated deterministically from [`scripts/art.py`](scripts/art.py) and catalog fields. They contain no upstream screenshots, product logos, or extracted game assets.

Slopforge's original SVG artwork and generation code are included under the repository's MIT license. The AI-generated forge raster is supplied as site branding; no exclusive copyright claim over generated imagery is asserted. Linked projects and their marks retain their respective rights.
