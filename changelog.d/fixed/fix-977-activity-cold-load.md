- The Discord Activity Playwright specs no longer fail their first attempt when another
  spec resets test data at the same time: the test stack's fake Discord instances now
  survive the reset's cache flush, and a missing one fails without calling Discord (#977).
