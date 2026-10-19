// Secondary reads (the nav badges) wait behind the page's own requests
// (step 6). In the browser host the engine answers one request at a time,
// and a badge queued first made Flights wait for it; the server answers
// requests side by side, so there is nothing to wait for.

/** Resolves after the requests the page has made so far. */
export async function afterPageRequests(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));     // let the page's effects queue theirs
  try {
    const { getRuntime } = await import("./engineClient");
    const { client } = await getRuntime();
    const idle = (client as { whenIdle?: () => Promise<void> }).whenIdle;
    if (idle) await idle.call(client);
  } catch {
    // No runtime to ask (a test's stand-in client): go ahead.
  }
}
