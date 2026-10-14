# Launch copy

Replace `fakebench.pages.dev` with the live domain before posting. If you include an average score, use the current number on the site.

## Hacker News (Show HN)

**Title:** Show HN: Can you tell real photos from AI? 20 images, 5 seconds each

**Text:**
I built a test to see how well people can tell real photos from AI images. You get 20 images and five seconds to decide on each. At the end, you can see your score, an estimated percentile, and the images you missed. For AI images, it also shows which model made them.

I'm also interested in how the scores change over time. The site shows the average accuracy across answers from the past seven days. It reflects the people and images on this site, so it's a starting point for comparison.

Real photos come from Wikimedia Commons with credits. AI images come from openly licensed datasets and optional generation runs. Every image gets the same crop and JPEG settings to reduce clues from file quality. The site runs on a Cloudflare Worker, with a weekly content refresh. Happy to answer questions about the image sources or how the rankings work.

https://fakebench.pages.dev/image

## Product Hunt

**Name:** FakeBench
**Tagline:** Real photo or AI? See how many you can get right
**Description:** You have five seconds to decide on each image. Get your score, see how it compares, and review the images you missed. Come back for a daily challenge with the same 10 images for everyone, or try another 20-image round.

## Reddit (r/InternetIsBeautiful, r/artificial)

**Title:** I made a test where you have 5 seconds to tell a real photo from an AI image

**Body:** It's called FakeBench: 20 images, five seconds each. Afterward, you get your score and can review the images you missed, including which model made the AI images. There's also a daily 10-image challenge. I'd like to hear which images caught you out. https://fakebench.pages.dev/image

## Reply templates (for comments, any platform)

- "What's the average score?" → "The current average is on the page. It's based on answers from the past seven days, or all results so far if there haven't been any recent tests."
- "Where do the images come from?" → "Real photos come from Wikimedia Commons and include credits. AI images come from Rapidata's openly licensed datasets and images generated for the project. We crop and save every image with the same settings."
- "Can it be cheated?" → "Yes. There's no account or verified testing session, so the scores depend on honest play. We limit submissions per IP when the rate limiter is enabled, but that doesn't make the average cheat-proof."
