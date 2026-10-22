// Chat Controller: Rendering, Speech, Feedback, Markdown
const Chat = {
  activeSpeechUtterance: null,
  speechRecognition: null,
  isRecording: false,

  init() {
    this.initSpeechRecognition();
  },

  // ----------------- Lightweight Robust Markdown Renderer -----------------
  renderMarkdown(text) {
    if (!text) return '';
    let html = text;

    // Escape raw HTML tags (prevent XSS)
    html = html.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    // Code blocks ```code```
    html = html.replace(/```([a-zA-Z0-9]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
    });

    // Citations `[DocName.pdf, p.1]` or [DocName.pdf, p.1]
    html = html.replace(/`?\[([a-zA-Z0-9_\-\.\s]+\.(?:pdf|docx|txt|md)),\s*p\.(\d+)\]`?/gi, (match, fname, page) => {
      const cleanFname = fname.trim();
      return `<span class="summary-citation-badge" onclick="PDFViewer.openDocumentByNameAndPage('${cleanFname}', ${page})" title="View ${cleanFname} Page ${page} in PDF Reader">📄 ${cleanFname} p.${page}</span>`;
    });

    // Inline code `code`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Headings ###
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Bold **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic *text*
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Blockquotes > quote
    html = html.replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>');

    // Bullet lists - item
    html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Numbered lists 1. item
    html = html.replace(/^\s*\d+\.\s+(.*$)/gim, '<li>$1</li>');

    // Paragraphs
    html = html.replace(/\n{2,}/g, '</p><p>');
    html = `<p>${html}</p>`;
    html = html.replace(/<p><\/p>/g, '');

    return html;
  },

  // ----------------- Voice Input (Web Speech API) -----------------
  initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      this.speechRecognition = new SpeechRecognition();
      this.speechRecognition.continuous = false;
      this.speechRecognition.interimResults = true;
      this.speechRecognition.lang = 'en-US';

      this.speechRecognition.onstart = () => {
        this.isRecording = true;
        const micBtn = document.getElementById('btn-voice-input');
        if (micBtn) micBtn.classList.add('mic-active');
      };

      this.speechRecognition.onresult = (event) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        const textarea = document.getElementById('chat-input-textarea');
        if (textarea && transcript) {
          textarea.value = transcript;
        }
      };

      this.speechRecognition.onerror = (event) => {
        console.warn('Speech recognition error:', event.error);
        this.stopSpeechRecognition();
      };

      this.speechRecognition.onend = () => {
        this.stopSpeechRecognition();
      };
    }
  },

  toggleVoiceInput() {
    if (!this.speechRecognition) {
      alert('Speech recognition is not supported in this browser. Please use Google Chrome, Edge, or a modern Chromium browser.');
      return;
    }

    if (this.isRecording) {
      this.speechRecognition.stop();
      this.stopSpeechRecognition();
    } else {
      try {
        this.speechRecognition.start();
      } catch (err) {
        console.error('Failed to start speech recognition:', err);
      }
    }
  },

  stopSpeechRecognition() {
    this.isRecording = false;
    const micBtn = document.getElementById('btn-voice-input');
    if (micBtn) micBtn.classList.remove('mic-active');
  },

  // ----------------- Voice Output (Read Answer Aloud) -----------------
  toggleReadAloud(text, btnElement) {
    if (!('speechSynthesis' in window)) {
      alert('Text-to-speech is not supported in this browser.');
      return;
    }

    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
      if (btnElement) {
        btnElement.classList.remove('speaking');
        btnElement.innerHTML = `<span>🔊</span> Read Aloud`;
      }
      return;
    }

    // Clean markdown before speaking
    const cleanText = text.replace(/[*#>`_]/g, '').replace(/\[.*?\]/g, '');
    this.activeSpeechUtterance = new SpeechSynthesisUtterance(cleanText);
    this.activeSpeechUtterance.rate = 1.0;
    this.activeSpeechUtterance.pitch = 1.0;

    if (btnElement) {
      btnElement.classList.add('speaking');
      btnElement.innerHTML = `<span>⏹</span> Stop Speaking`;
    }

    this.activeSpeechUtterance.onend = () => {
      if (btnElement) {
        btnElement.classList.remove('speaking');
        btnElement.innerHTML = `<span>🔊</span> Read Aloud`;
      }
    };

    this.activeSpeechUtterance.onerror = () => {
      if (btnElement) {
        btnElement.classList.remove('speaking');
        btnElement.innerHTML = `<span>🔊</span> Read Aloud`;
      }
    };

    window.speechSynthesis.speak(this.activeSpeechUtterance);
  },

  // ----------------- Utilities: Copy & Feedback -----------------
  copyToClipboard(text, btnElement) {
    navigator.clipboard.writeText(text).then(() => {
      const original = btnElement.innerHTML;
      btnElement.innerHTML = `<span>✓</span> Copied!`;
      btnElement.style.color = 'var(--success)';
      setTimeout(() => {
        btnElement.innerHTML = original;
        btnElement.style.color = '';
      }, 2000);
    }).catch(err => {
      console.error('Failed to copy text:', err);
    });
  },

  giveFeedback(btnElement, type) {
    btnElement.style.color = type === 'up' ? 'var(--success)' : 'var(--danger)';
    btnElement.parentElement.querySelectorAll('.btn-msg-action').forEach(b => {
      if (b !== btnElement && (b.innerText.includes('👍') || b.innerText.includes('👎'))) {
        b.style.opacity = '0.4';
        b.style.pointerEvents = 'none';
      }
    });
  }
};
