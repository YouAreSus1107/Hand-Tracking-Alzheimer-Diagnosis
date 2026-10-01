"""
Keyboard shortcuts shared by the live tests.

S skips a practice phase (spiral practice, the paced-tapping warm-up, each
eye-test part's practice trials) and goes straight to the scored part. It is
a no-op anywhere else, so a stray press during a scored run changes nothing.
A skip is saved as `raw.practice_skipped` on the session.

The eye test is the exception: it has three separate parts, and anywhere
inside a part other than its practice S skips the whole part (so from
practice, S twice). Skipped parts are saved as `raw.parts_skipped` and left
out of the report; a run with every part skipped is not saved at all.

V hides every overlay (panels, prompts, status bar, the spiral template) and
leaves only the camera picture -- with the hand skeleton where the test draws
one -- so a clinician can show the patient where their hand is and correct
it. V again brings the overlay back. The test keeps running underneath;
on-screen buttons ignore clicks while hidden (they cannot be seen), but the
keyboard still works.
"""

SKIP_PRACTICE = (ord("s"), ord("S"))
SKIP_HINT = "S  skip practice"
SKIP_PART_HINT = "S  skip this part"

TOGGLE_OVERLAY = (ord("v"), ord("V"))
OVERLAY_HIDDEN_HINT = "V  show instructions"
