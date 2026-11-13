# VK publishing status — 2026-11-13

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
