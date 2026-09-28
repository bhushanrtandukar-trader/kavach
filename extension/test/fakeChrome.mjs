// A minimal in-memory stand-in for the `chrome` extension APIs the controller uses.
export function fakeChrome({ activeTabUrl = "https://github.com/login", tabId = 1 } = {}) {
  const local = new Map();
  const session = new Map();
  const storageArea = (map) => ({
    async get(keys) {
      const out = {};
      const list = keys == null ? [...map.keys()] : Array.isArray(keys) ? keys : [keys];
      for (const k of list) if (map.has(k)) out[k] = map.get(k);
      return out;
    },
    async set(obj) {
      for (const [k, v] of Object.entries(obj)) map.set(k, v);
    },
    async remove(keys) {
      for (const k of Array.isArray(keys) ? keys : [keys]) map.delete(k);
    },
  });

  const messages = []; // messages sent to a content-script tab, via chrome.tabs.sendMessage
  let nextTabResponse = { filled: true };

  return {
    runtime: { id: "kavach-test-id" },
    storage: { local: storageArea(local), session: storageArea(session) },
    tabs: {
      async query() {
        return [{ id: tabId, url: activeTabUrl }];
      },
      async sendMessage(id, msg) {
        messages.push({ id, msg });
        return nextTabResponse;
      },
    },
    action: {
      async setBadgeText() {},
      async setBadgeBackgroundColor() {},
    },
    _messages: messages,
    _setTabResponse: (r) => (nextTabResponse = r),
    _maps: { local, session },
  };
}
