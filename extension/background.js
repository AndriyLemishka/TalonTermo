chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.action === 'open_extensions') {
    const extUrl = `chrome://extensions/?id=${chrome.runtime.id}`;
    if (sender.tab && sender.tab.id) {
      chrome.tabs.update(sender.tab.id, { url: extUrl }, () => {
        if (chrome.runtime.lastError) {
          chrome.tabs.create({ url: extUrl });
        }
      });
    } else {
      chrome.tabs.create({ url: extUrl });
    }
    sendResponse({ ok: true });
  }
});
