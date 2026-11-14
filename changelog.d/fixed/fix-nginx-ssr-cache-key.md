- Pages that read query parameters, such as `/events?organization=N`, no longer share one
  cached server render with their unfiltered URL, which showed the wrong filter or tab and
  caused a hydration error until the nginx SSR cache expired.
