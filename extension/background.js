// Service worker: wires the controller to the browser's message channel.
import { createController } from './lib/controller.js';

const controller = createController({ chrome });

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  controller.handle(msg, sender).then(sendResponse, () => sendResponse({ ok: false, message: 'Something went wrong.' }));
  return true; // keep the channel open for the async answer
});

// Nothing is kept in the worker between wake-ups: the session lives in chrome.storage.session.
