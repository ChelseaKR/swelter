import { MessageFormat } from "./vendor/messageformat/index.js";

// app.js remains a plain browser script loaded as a module. Expose exactly the pinned canonical
// MF2 formatter it needs without bundling or fetching any runtime code from a third party.
globalThis.SwelterMessageFormat = MessageFormat;
