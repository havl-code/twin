const SUGGESTIONS = [
  { icon: "💼", text: "Tell me about your background and experience." },
  { icon: "🚀", text: "What kinds of projects are you working on now?" },
  { icon: "🛠️", text: "What are your strongest technical skills?" },
  { icon: "📬", text: "How can I get in touch with you?" },
  { icon: "✨", text: "What's a fun fact most people don't know about you?" },
];

const PLACEHOLDERS = [
  "Type your question...",
  "What do you want to know about Hà?",
  "Ask about experience, projects, or skills...",
  "How can I get in touch with Hà?",
];

const messagesEl = document.getElementById("messages");
const emptyStateEl = document.getElementById("empty-state");
const suggestionGridEl = document.getElementById("suggestion-grid");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");

let history = [];
let busy = false;

document.title = "Hà's Digital Twin";

function renderMarkdown(text) {
  const html = marked.parse(text, { breaks: true });
  return DOMPurify.sanitize(html);
}

function scrollToBottom() {
  const panel = messagesEl.closest(".chat-panel");
  panel.scrollTop = panel.scrollHeight;
}

function addUserBubble(text) {
  const row = document.createElement("div");
  row.className = "msg-row user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  scrollToBottom();
}

function addAssistantBubble() {
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "⚡";
  const bubble = document.createElement("div");
  bubble.className = "bubble typing";
  bubble.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  scrollToBottom();
  return bubble;
}

function setBusy(isBusy) {
  busy = isBusy;
  inputEl.disabled = isBusy;
  sendBtn.disabled = isBusy;
}

function autoResize() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}

async function sendMessage(text) {
  const trimmed = text.trim();
  if (!trimmed || busy) return;

  if (emptyStateEl) emptyStateEl.remove();

  const historyToSend = history.slice();
  history.push({ role: "user", content: trimmed });

  addUserBubble(trimmed);
  inputEl.value = "";
  autoResize();
  setBusy(true);

  const bubble = addAssistantBubble();
  let full = "";
  let firstToken = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: trimmed, history: historyToSend }),
    });

    if (!res.ok || !res.body) {
      throw new Error(`Request failed: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      if (!chunk) continue;
      if (firstToken) {
        bubble.classList.remove("typing");
        bubble.innerHTML = "";
        firstToken = false;
      }
      full += chunk;
      bubble.innerHTML = renderMarkdown(full);
      scrollToBottom();
    }

    history.push({ role: "assistant", content: full });
  } catch (err) {
    bubble.classList.remove("typing");
    bubble.innerHTML = '<span class="error-text">Sorry, something went wrong, please try again.</span>';
    console.error(err);
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(inputEl.value);
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage(inputEl.value);
  }
});

inputEl.addEventListener("input", autoResize);

SUGGESTIONS.forEach(({ icon, text }) => {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "suggestion-card";
  card.innerHTML = `<span class="suggestion-icon">${icon}</span><span>${text}</span>`;
  card.addEventListener("click", () => sendMessage(text));
  suggestionGridEl.appendChild(card);
});

// Cycle the placeholder text while the input is empty and unfocused.
let placeholderIndex = 0;
setInterval(() => {
  if (inputEl.value || document.activeElement === inputEl) return;
  placeholderIndex = (placeholderIndex + 1) % PLACEHOLDERS.length;
  inputEl.placeholder = PLACEHOLDERS[placeholderIndex];
}, 3200);

inputEl.focus();
