# VK publishing status

## Current state: 2026-11-14 (authoritative)

- Native VK RSS import has produced actual visible current news images, confirmed
  by the owner. API wall publishing is disabled through VK_WALL_ENABLED=0.
- Native ordinary RSS posts truncate long bodies. The complete Telegram caption
  and continuation are present in RSS; this is not resolved for normal wall posts.
  wall.edit access diagnostics: community error 27, personal token error 9.
- rss-vk.xml now keeps real paragraph breaks within a single HTML text node and
  exports complete descriptions. New posts after vk_rss_format_since.txt receive
  vk.cc links, sport emoji, per-paragraph formatting and topic/surname hashtags.
  Incomplete Telegram news waits for its continuation before entering RSS.
- Optional rss-vk-article.xml is prepared for full-text VK articles, using normal
  HTML paragraphs and original images. It starts at vk_rss_article_since.txt to
  avoid replaying old news. Switching VK to this format awaits the owner's choice.
- Dzen mirror excludes single forecasts, full analyses, goals and live betting
  noise. No daily quota. Match-start covers now use actual team logos/flags or
  player portraits and never contain betting predictions or odds.
- The existing mirror post https://t.me/aistavvit_dzen/551 was updated with the
  new Japan/Brazil cover and the live image was visually verified.
- The owner will delete VK test posts personally; do not delete them automatically.

Older diagnostic history follows; earlier archive-fallback settings are superseded.


## Confirmed working

Community photo stories: `stories.getPhotoUploadServer` → multipart `file` upload →
`stories.save` → `stories.getById`, all using `VK_TOKEN`.

Live test: https://vk.com/story-228963529_456239018.
The API confirmed a photo in the saved story. Automatic stories are enabled in
`daily.yml`; wall publishing uses the verified archive-photo route below. Stories start after the bootstrap cursor,
with a 15-minute minimum gap and a 16-per-day cap.

## Confirmed unsuccessful

Test https://vk.com/wall-228963529_416 used the photo ID returned by the verified
story, its actual owner ID, and its access key when present. `wall.post` returned
the post ID, but the owner inspected the post and confirmed it has no image.
Do not enable story-photo-to-wall publishing based on a successful `wall.post`
response alone. This test does not establish that every possible story-sharing
method fails; it specifically rules out the tested direct photo attachment.

The current user token has `photos`, `wall`, and `offline` permission bits, but
wall-photo uploads, album reads, wall reads, and link parsing returned error 9.
Reauthorization did not resolve the observed wall-photo upload failure.
A direct URL attachment returned `link_photo_sizing_rule: No photo given`.
Community-token link parsing returned error 27.

Keep signed upload URLs, tokens, and photo access keys out of logs.

## Verified wall route (enabled)

The owner confirmed visible ordinary photos in posts 418 and 419:
https://vk.com/wall-228963529_418 and https://vk.com/wall-228963529_419.
Both use the historical attachment `photo394825865_457255433`; the public
reference works without a photo access key. This reuses an archive illustration,
not a newly uploaded image for each news item. Posts explicitly label it as an
archive illustration. Fresh unique cards continue to publish in stories.

Live post https://vk.com/wall-228963529_420 additionally passed independent
community Long Poll `wall_post_new` photo-attachment verification. A comment
containing a VK-shortened site link was successfully created using the community
token. Evidence: GitHub Actions run 43480465870 (event-photo diagnostic).

Production uses repository variable VK_WALL_RESERVE_PHOTO with that public ID,
starts the event monitor before posting, persists the created post ID and event
cursor before checking, and holds uncertain posts instead of blindly duplicating
them. Short-link comments use a stable guid. Activation preserves the old pending
post for review and starts with future Telegram posts; it does not replay backlog.
The existing minimum gap and hourly/daily caps still apply. Access or availability
of an external VK photo can change; no successful wall.post response alone is
accepted as proof of a photo attachment.

## Fresh-photo checks and automatic recovery

2026-11-13: fresh-wall run 43484152939 failed at photos.getWallUploadServer
with error 9. The historical community chat upload (run 43484363181) saved a
new photo394825865_457255546, but wall event verification found no photo in
test post 422. A positive user owner ID alone is therefore insufficient proof.
The personal message uploader (run 43484684328) also returned error 9 at
photos.getMessagesUploadServer. No messages were sent by these diagnostics.

VK_WALL_PREFER_FRESH=1 enables the real per-post image as first choice when
personal-token uploads become available. On upload failure it keeps the labeled
archive fallback, with independent six-hour retry backoff for Flood control
(one hour for other errors). VK_WALL_FRESH_NOT_BEFORE sets an initial upload
cooldown after these confirmed failures. Successful recovery removes the archive
caption and uses the newly saved per-post attachment. The same community wall
verification and short-link comments are retained. Unique images on the wall are
NOT confirmed working with the current restricted personal token.

## Update 2026-11-14: only current per-post photos

VK_WALL_REQUIRE_FRESH=1 now disables archive substitution, even if the old
VK_WALL_RESERVE_PHOTO variable remains configured. A wall post waits for its own
newly uploaded image; a configured archive cannot satisfy that requirement.
Community event verification and short-link comments remain enabled. Upload
cooldowns are respected independently. The latest live state still records
photos.getWallUploadServer error 9; unique wall uploads remain unconfirmed.

The Telegram mirror @aistavvit_dzen has separate editorial delivery rules:
news, bot statistics, daily match schedules, match starts, expresses and final
express results, and day/week/month summaries. Individual forecasts, full match
analyses, forecast digests, goals, live forecasts, per-match results and partial
express updates are excluded. No daily quota is applied. Starts are sanitized in
both caption and newly rendered image. Source IDs and content keys deduplicate
direct news delivery and channel-copy retries. Old news/starts are skipped rather
than replayed after downtime; successful deliveries checkpoint state.
