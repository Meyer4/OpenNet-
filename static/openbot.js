/* OpenBot chat behaviour. Talks to the Flask endpoint in app.py. */
(function () {
  'use strict';

  var config = window.OPENBOT_CONFIG || {};
  var chatContainer = document.getElementById('chat-container');
  var input = document.getElementById('chat-input');
  var sendBtn = document.getElementById('send-btn');
  var voiceBtn = document.getElementById('voice-btn');
  var filePicker = document.getElementById('file-picker');

  function syncSendButton() {
    sendBtn.disabled = !input.value.trim();
  }

  input.addEventListener('input', function () {
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';
    syncSendButton();
  });

  function addMessage(text, sender, source) {
    var msg = document.createElement('div');
    msg.classList.add('message', sender === 'user' ? 'user-msg' : 'ai-msg');
    msg.setAttribute('role', 'article');

    var body = document.createElement('span');
    body.textContent = text;
    msg.appendChild(body);

    if (source) {
      var src = document.createElement('span');
      src.className = 'source';
      src.textContent = 'Source: ' + source;
      msg.appendChild(src);
    }

    var ts = document.createElement('div');
    ts.className = 'timestamp';
    ts.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    msg.appendChild(ts);

    chatContainer.appendChild(msg);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  function showTypingIndicator() {
    removeTypingIndicator();
    var typing = document.createElement('div');
    typing.id = 'typing-indicator';
    typing.setAttribute('aria-live', 'assertive');
    typing.textContent = 'AI is typing';
    for (var i = 0; i < 3; i++) {
      var dot = document.createElement('span');
      dot.className = 'dot';
      typing.appendChild(dot);
    }
    chatContainer.appendChild(typing);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  function removeTypingIndicator() {
    var typing = document.getElementById('typing-indicator');
    if (typing) { typing.remove(); }
  }

  // Ask the Flask API when there is one; on a static host, or if the API is
  // unavailable, answer in the browser from the bundled documents.
  async function askApi(text) {
    var res = await fetch(config.apiUrl || '/openbot/api', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text })
    });
    var data = await res.json();
    if (!res.ok) { throw new Error(data.error || ('Request failed (' + res.status + ')')); }
    return { answer: data.answer, source: data.source };
  }

  async function askLocally(text) {
    var matches = await window.OpenBotSearch.search(text, config.docsUrl, 3);
    if (!matches.length) {
      return { answer: "I couldn't find anything about that in your documents.", source: null };
    }
    var top = matches[0];
    return {
      answer: top.kind === 'title'
        ? 'There is a document called \u201c' + top.name + '\u201d that looks relevant.'
        : top.snippet,
      source: top.name
    };
  }

  async function sendMessage() {
    var text = input.value.trim();
    if (!text) { return; }

    addMessage(text, 'user');
    input.value = '';
    input.style.height = 'auto';
    syncSendButton();
    input.focus();
    showTypingIndicator();

    var reply;
    try {
      reply = config.staticBuild ? await askLocally(text) : await askApi(text);
    } catch (apiError) {
      try {
        reply = await askLocally(text);
      } catch (localError) {
        reply = { answer: 'Error contacting OpenBot.', source: null };
      }
    }

    removeTypingIndicator();
    addMessage(reply.answer, 'ai', reply.source);
  }

  sendBtn.addEventListener('click', sendMessage);

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Voice input via the Web Speech API, where the browser supports it.
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceBtn.disabled = true;
    voiceBtn.title = 'Voice input is not supported in this browser';
  } else {
    var recognition = new SpeechRecognition();
    var listening = false;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = function (event) {
      input.value = event.results[0][0].transcript;
      input.dispatchEvent(new Event('input'));
    };
    recognition.onend = function () {
      listening = false;
      voiceBtn.classList.remove('active');
      voiceBtn.setAttribute('aria-pressed', 'false');
    };
    voiceBtn.addEventListener('click', function () {
      if (listening) { recognition.stop(); return; }
      listening = true;
      voiceBtn.classList.add('active');
      voiceBtn.setAttribute('aria-pressed', 'true');
      recognition.start();
    });
  }

  filePicker.addEventListener('change', function () {
    var file = filePicker.files && filePicker.files[0];
    if (file) { addMessage('Attached: ' + file.name, 'user'); }
  });

  addMessage('Hi! Ask me about the OpenNet documents.', 'ai');
})();
