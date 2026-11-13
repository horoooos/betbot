# VK publishing status — 2026-11-13

## Confirmed working

Community photo stories: `stories.getPhotoUploadServer` → multipart `file` upload →
`stories.save` → `stories.getById`, all using `VK_TOKEN`.

Live test: https://vk.com/story-228963529_456239018.
The API confirmed a photo in the saved story. Automatic stories are enabled in
`daily.yml`; wall publishing is disabled. Stories start after the bootstrap cursor,
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
