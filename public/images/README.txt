DROP YOUR PHOTOS HERE
=====================

This folder holds the photos shown in galleries on the site (talks, prizes,
community events).

HOW IT WORKS
------------
1. Put image files in this folder, e.g.:
     public/images/devoxx25-1.jpg
     public/images/phd-defense-1.jpg

2. Open  src/data/site.ts  and add the filenames to the matching item's
   `images:` array, e.g.:

     {
       year: "2025",
       event: "Devoxx Morocco 2025",
       ...
       images: ["devoxx25-1.jpg", "devoxx25-2.jpg"],   <-- here
     }

3. Save. The gallery thumbnails appear automatically; clicking one opens a
   full-screen lightbox (arrow keys / Esc work too).

NOTES
-----
- Leave  images: []  empty for any talk/prize/event that has NO photos.
  That item simply shows text only — no broken galleries.
- If you list a filename that isn't uploaded yet, a tasteful
  "photo soon" tile shows instead of a broken image, so you can add the
  data now and the photos later.
- Square-ish photos (1:1) look best as thumbnails; any size works.
- Recommended: keep each image under ~500 KB for fast loading.
