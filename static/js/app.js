// Main Application Controller for DocuMind AI
const App = {
  state: {
    currentConvId: null,
    documents: [],
    selectedDocIds: new Set(),
    selectedChapter: 'All Chapters',
    currentStyle: 'Detailed',
    conversations: [],
    stats: {},
    lastQuestion: '',
    isLoading: false,
    settings: {},

    // Quiz State
    currentQuiz: {
      questions: [],
      currentIndex: 0,
      score: 0,
      answered: false
    },

    // Flashcards State
    currentFlashcards: {
      cards: [],
      currentIndex: 0,
      isFlipped: false,
      mastered: new Set()
    },

    // Concept Map State
    currentConceptMap: {
      data: null,
      zoom: 1.0,
      selectedNodeId: null
    },

    // Smart Summary State
    currentSmartSummary: {
      text: '',
      docNames: []
    }
  },

  async init() {
    Chat.init();
    this.initTheme();
    this.bindEvents();
    
    // Initial data load
    await Promise.all([
      this.loadSettings(),
      this.loadDocuments(),
      this.loadConversations(),
      this.loadDashboardStats()
    ]);

    if (this.state.conversations.length > 0) {
      await this.selectConversation(this.state.conversations[0].id);
    } else {
      this.renderDashboard();
    }
  },

  // ----------------- Theme Management -----------------
  initTheme() {
    const savedTheme = localStorage.getItem('documind_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    const themeIcon = document.getElementById('theme-icon');
    if (themeIcon) {
      themeIcon.innerText = savedTheme === 'dark' ? '☀️' : '🌙';
    }
  },

  toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('documind_theme', next);
    const themeIcon = document.getElementById('theme-icon');
    if (themeIcon) {
      themeIcon.innerText = next === 'dark' ? '☀️' : '🌙';
    }
  },

  // ----------------- Style Selector -----------------
  setStyle(styleName) {
    this.state.currentStyle = styleName;
    document.querySelectorAll('.style-pill-btn').forEach(btn => {
      if (btn.getAttribute('data-style') === styleName) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Provide subtle feedback in input placeholder
    const textarea = document.getElementById('chat-input-textarea');
    if (textarea) {
      textarea.placeholder = `Ask a question (Answering in ${styleName} style)...`;
    }
  },

  // ----------------- Data Loading -----------------
  async loadSettings() {
    try {
      this.state.settings = await API.getSettings();
      this.updateProviderBadge();
    } catch (err) {
      console.error('Failed to load settings:', err);
    }
  },

  updateProviderBadge() {
    const badge = document.getElementById('provider-status-badge');
    if (!badge) return;
    const provider = this.state.settings.active_provider || 'local';
    const hasKey = (provider === 'gemini' && this.state.settings.has_gemini_key) ||
                   (provider === 'openai' && this.state.settings.has_openai_key) ||
                   (provider === 'groq' && this.state.settings.has_groq_key);

    if (hasKey) {
      badge.innerText = `${provider.toUpperCase()} ONLINE`;
      badge.style.background = 'rgba(16, 185, 129, 0.15)';
      badge.style.color = 'var(--success)';
      badge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
    } else {
      badge.innerText = `LOCAL RAG MODE`;
      badge.style.background = 'var(--accent-soft)';
      badge.style.color = 'var(--accent-primary)';
      badge.style.borderColor = 'rgba(168, 85, 247, 0.35)';
    }
  },

  async loadDocuments(search = '') {
    try {
      const res = await API.getDocuments(search);
      this.state.documents = res.documents || [];
      
      // Auto-select all by default if none selected
      if (this.state.selectedDocIds.size === 0) {
        this.state.documents.forEach(d => this.state.selectedDocIds.add(d.id));
      }
      
      this.renderDocumentList();
      this.updateSelectedDocPill();
      this.updateFeatureDocSelects();
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  },

  async loadConversations() {
    try {
      const res = await API.getConversations();
      this.state.conversations = res.conversations || [];
      this.renderConversationList();
    } catch (err) {
      console.error('Failed to load conversations:', err);
    }
  },

  async loadDashboardStats() {
    try {
      this.state.stats = await API.getDashboardStats();
      this.updateStatsCards();
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  },

  updateStatsCards() {
    const s = this.state.stats;
    const docEl = document.getElementById('stat-docs');
    const pageEl = document.getElementById('stat-pages');
    const chunkEl = document.getElementById('stat-chunks');
    const qEl = document.getElementById('stat-questions');

    if (docEl) docEl.innerText = s.documents_count || 0;
    if (pageEl) pageEl.innerText = s.pages_processed || 0;
    if (chunkEl) chunkEl.innerText = s.chunks_indexed || 0;
    if (qEl) qEl.innerText = s.questions_asked || 0;
  },

  // ----------------- UI Rendering -----------------
  renderDocumentList() {
    const container = document.getElementById('document-list-container');
    if (!container) return;

    if (this.state.documents.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding: 24px 10px; color: var(--text-muted); font-size: 12px;">
          No documents uploaded yet.<br>Drop files above to begin.
        </div>
      `;
      return;
    }

    container.innerHTML = this.state.documents.map(doc => {
      const isChecked = this.state.selectedDocIds.has(doc.id);
      const ext = doc.file_type.toLowerCase();
      const chapters = doc.chapters || [];

      return `
        <div class="doc-item-card" data-doc-id="${doc.id}">
          <div class="doc-item-main">
            <input type="checkbox" class="doc-checkbox" ${isChecked ? 'checked' : ''} onchange="App.toggleDocSelection('${doc.id}')">
            <div class="doc-icon-badge ${ext}">${ext}</div>
            <div class="doc-info" onclick="PDFViewer.openDocumentPage('${doc.id}', '${doc.filename}', 1, ${doc.page_count})" style="cursor:pointer;" title="Click to view document">
              <div class="doc-name">${doc.filename}</div>
              <div class="doc-meta">
                <span>${doc.page_count} pg${doc.page_count > 1 ? 's' : ''}</span>
                <span>•</span>
                <span>${doc.file_size_formatted || ''}</span>
                <span>•</span>
                <span>${doc.chunk_count} chunks</span>
              </div>
            </div>
            <button class="doc-btn-delete" title="Delete document" onclick="App.deleteDocument('${doc.id}')">
              🗑
            </button>
          </div>

          ${doc.is_scanned ? `
            <div style="font-size:10px; color:var(--warning); padding: 3px 8px; background: rgba(245,158,11,0.12); border-radius:4px; font-weight:600;">
              ⚠️ Scanned document (OCR recommended)
            </div>
          ` : ''}

          ${chapters.length > 0 ? `
            <button class="doc-chapters-toggle" onclick="App.toggleChaptersList('${doc.id}')">
              <span>📖</span> ${chapters.length} Chapters detected ▾
            </button>
            <div class="doc-chapters-list" id="chapters-list-${doc.id}">
              ${chapters.map(ch => `
                <div class="chapter-pill" onclick="App.filterByChapter('${ch.title}')">
                  <span>${ch.number}. ${ch.title}</span>
                  <span style="color:var(--text-muted);">p.${ch.start_page}</span>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>
      `;
    }).join('');
  },

  renderConversationList() {
    const container = document.getElementById('conversations-list-container');
    if (!container) return;

    if (this.state.conversations.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding: 24px 10px; color: var(--text-muted); font-size: 12px;">
          No conversations yet.
        </div>
      `;
      return;
    }

    container.innerHTML = this.state.conversations.map(conv => {
      const isActive = conv.id === this.state.currentConvId;
      return `
        <div class="conv-item ${isActive ? 'active' : ''}" onclick="App.selectConversation('${conv.id}')">
          <div class="conv-title" title="${conv.title}">💬 ${conv.title}</div>
          <div class="conv-actions">
            <button class="btn-icon-xs" title="Rename" onclick="event.stopPropagation(); App.promptRenameConversation('${conv.id}', '${conv.title}')">✏️</button>
            <button class="btn-icon-xs" title="Delete" onclick="event.stopPropagation(); App.deleteConversation('${conv.id}')">🗑</button>
          </div>
        </div>
      `;
    }).join('');
  },

  updateSelectedDocPill() {
    const pill = document.getElementById('header-doc-selection-pill');
    if (!pill) return;

    const total = this.state.documents.length;
    const selected = this.state.selectedDocIds.size;

    if (total === 0) {
      pill.innerText = 'No Documents';
      pill.style.background = 'rgba(244, 63, 94, 0.12)';
      pill.style.color = 'var(--danger)';
    } else if (selected === total) {
      pill.innerText = `Searching All Documents (${total})`;
      pill.style.background = 'var(--accent-soft)';
      pill.style.color = 'var(--accent-primary)';
    } else if (selected === 0) {
      pill.innerText = `No Documents Selected`;
      pill.style.background = 'rgba(245, 158, 11, 0.15)';
      pill.style.color = 'var(--warning)';
    } else {
      pill.innerText = `Searching ${selected} of ${total} Documents`;
      pill.style.background = 'rgba(16, 185, 129, 0.15)';
      pill.style.color = 'var(--success)';
    }
  },

  updateFeatureDocSelects() {
    const singleSelects = [
      document.getElementById('quiz-doc-select'),
      document.getElementById('flashcard-doc-select')
    ];

    singleSelects.forEach(select => {
      if (!select) return;
      if (this.state.documents.length === 0) {
        select.innerHTML = '<option value="">No documents uploaded</option>';
        return;
      }
      select.innerHTML = this.state.documents.map(d => `
        <option value="${d.id}">${d.filename}</option>
      `).join('');
    });

    // Multi-doc capable selects: Concept Map and Smart Summarizer
    const multiSelects = [
      document.getElementById('concept-map-doc-select'),
      document.getElementById('summarizer-doc-select')
    ];

    multiSelects.forEach(select => {
      if (!select) return;
      if (this.state.documents.length === 0) {
        select.innerHTML = '<option value="">No documents uploaded</option>';
        return;
      }
      let optionsHtml = '';
      if (this.state.documents.length > 1) {
        optionsHtml += `<option value="__all__">📚 All Selected Documents (${this.state.selectedDocIds.size || this.state.documents.length})</option>`;
      }
      optionsHtml += this.state.documents.map(d => `
        <option value="${d.id}">${d.filename}</option>
      `).join('');
      select.innerHTML = optionsHtml;
    });

    this.onSummarizerDocChange();
    this.onQuizDocChange();
    this.onFlashcardDocChange();
  },

  onSummarizerDocChange() {
    const docSelect = document.getElementById('summarizer-doc-select');
    const chGroup = document.getElementById('summarizer-chapter-group');
    if (!docSelect) return;
    if (docSelect.value === '__all__') {
      if (chGroup) chGroup.style.display = 'none';
    } else {
      if (chGroup) chGroup.style.display = 'block';
      this._populateChapterSelect('summarizer-doc-select', 'summarizer-chapter-select');
    }
  },

  onQuizDocChange() {
    this._populateChapterSelect('quiz-doc-select', 'quiz-chapter-select');
  },

  onFlashcardDocChange() {
    this._populateChapterSelect('flashcard-doc-select', 'flashcard-chapter-select');
  },

  _populateChapterSelect(docSelectId, chapterSelectId) {
    const docSelect = document.getElementById(docSelectId);
    const chapterSelect = document.getElementById(chapterSelectId);
    if (!docSelect || !chapterSelect) return;

    const docId = docSelect.value;
    const doc = this.state.documents.find(d => d.id === docId);

    chapterSelect.innerHTML = '<option value="All Chapters">Entire Document</option>';
    if (doc && doc.chapters && doc.chapters.length > 0) {
      doc.chapters.forEach(ch => {
        const opt = document.createElement('option');
        opt.value = ch.title;
        opt.innerText = `Chapter ${ch.number}: ${ch.title}`;
        chapterSelect.appendChild(opt);
      });
    }
  },

  openInspectorTab(tabName) {
    const tabBtn = document.querySelector(`[data-inspector-tab="${tabName}"]`);
    if (tabBtn) tabBtn.click();
    const inspector = document.getElementById('inspector-panel');
    if (inspector && inspector.classList.contains('collapsed')) {
      inspector.classList.remove('collapsed');
    }
  },

  // ----------------- Event Bindings -----------------
  bindEvents() {
    // Sidebar Tabs
    document.querySelectorAll('[data-sidebar-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-sidebar-tab');
        document.querySelectorAll('[data-sidebar-tab]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        document.querySelectorAll('.sidebar-pane').forEach(p => p.classList.remove('active'));
        const pane = document.getElementById(`sidebar-pane-${tab}`);
        if (pane) pane.classList.add('active');
      });
    });

    // Inspector Tabs
    document.querySelectorAll('[data-inspector-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-inspector-tab');
        document.querySelectorAll('[data-inspector-tab]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        document.querySelectorAll('.inspector-pane').forEach(p => p.classList.remove('active'));
        const pane = document.getElementById(`inspector-pane-${tab}`);
        if (pane) pane.classList.add('active');
      });
    });

    // Panel Toggles
    const toggleLeft = document.getElementById('btn-toggle-sidebar');
    if (toggleLeft) {
      toggleLeft.addEventListener('click', () => {
        document.getElementById('sidebar').classList.toggle('collapsed');
      });
    }

    const toggleRight = document.getElementById('btn-toggle-inspector');
    if (toggleRight) {
      toggleRight.addEventListener('click', () => {
        document.getElementById('inspector-panel').classList.toggle('collapsed');
      });
    }

    // Document Search Filter
    const searchInput = document.getElementById('doc-search-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.loadDocuments(e.target.value.trim());
      });
    }

    // Select All Checkbox
    const selectAllCheckbox = document.getElementById('select-all-docs');
    if (selectAllCheckbox) {
      selectAllCheckbox.addEventListener('change', (e) => {
        if (e.target.checked) {
          this.state.documents.forEach(d => this.state.selectedDocIds.add(d.id));
        } else {
          this.state.selectedDocIds.clear();
        }
        this.renderDocumentList();
        this.updateSelectedDocPill();
      });
    }

    // Chat Input Form / Textarea
    const textarea = document.getElementById('chat-input-textarea');
    if (textarea) {
      textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.handleSendMessage();
        }
      });
      // Auto-grow textarea
      textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
      });
    }

    const sendBtn = document.getElementById('btn-send-message');
    if (sendBtn) {
      sendBtn.addEventListener('click', () => this.handleSendMessage());
    }

    // Voice Input Mic Button
    const voiceBtn = document.getElementById('btn-voice-input');
    if (voiceBtn) {
      voiceBtn.addEventListener('click', () => Chat.toggleVoiceInput());
    }

    // File Upload via Dropzone & Input
    const dropzone = document.getElementById('upload-dropzone');
    const fileInput = document.getElementById('file-upload-input');

    if (dropzone && fileInput) {
      dropzone.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          this.handleFileUpload(Array.from(e.target.files));
          fileInput.value = '';
        }
      });

      dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });

      dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
      });

      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
          this.handleFileUpload(Array.from(e.dataTransfer.files));
        }
      });
    }

    // Quick Attach Button
    const quickAttachBtn = document.getElementById('btn-quick-attach');
    if (quickAttachBtn && fileInput) {
      quickAttachBtn.addEventListener('click', () => fileInput.click());
    }

    // Clear Chat Button
    const clearChatBtn = document.getElementById('btn-clear-chat');
    if (clearChatBtn) {
      clearChatBtn.addEventListener('click', () => this.clearCurrentChat());
    }

    // New Chat Button
    const newChatBtn = document.getElementById('btn-new-chat');
    if (newChatBtn) {
      newChatBtn.addEventListener('click', () => this.createNewChat());
    }
  },

  // ----------------- Multi-stage File Upload -----------------
  async handleFileUpload(files) {
    if (!files || files.length === 0) return;

    this.showUploadModal(files.map(f => f.name));

    try {
      this.updateUploadModalStep(1, 'Uploading files to server...');
      await new Promise(r => setTimeout(r, 400));

      this.updateUploadModalStep(2, 'Extracting text and structure...');
      await API.uploadDocuments(files);

      this.updateUploadModalStep(3, 'Detecting chapters and sections...');
      await new Promise(r => setTimeout(r, 400));

      this.updateUploadModalStep(4, 'Splitting chunks with contextual overlaps...');
      await new Promise(r => setTimeout(r, 400));

      this.updateUploadModalStep(5, 'Generating high-dimensional semantic embeddings...');
      await new Promise(r => setTimeout(r, 400));

      this.updateUploadModalStep(6, 'Indexing complete! Ready to ask questions.', true);

      // Refresh documents and stats
      await this.loadDocuments();
      await this.loadDashboardStats();

      setTimeout(() => {
        this.closeUploadModal();
      }, 1100);

    } catch (err) {
      this.updateUploadModalError(err.message || 'Upload failed');
    }
  },

  showUploadModal(filenames) {
    const modal = document.getElementById('upload-progress-modal');
    const filesList = document.getElementById('upload-modal-files-list');
    if (filesList) {
      filesList.innerText = `Processing: ${filenames.join(', ')}`;
    }
    if (modal) modal.classList.add('active');
  },

  updateUploadModalStep(stepNum, text, isFinal = false) {
    const stepEl = document.getElementById(`upload-step-${stepNum}`);
    const textEl = document.getElementById('upload-modal-status-text');

    if (textEl) textEl.innerText = text;
    if (stepEl) {
      stepEl.classList.add('completed');
      stepEl.querySelector('.stage-icon').innerHTML = '✓';
    }
    const nextStep = document.getElementById(`upload-step-${stepNum + 1}`);
    if (nextStep && !isFinal) {
      nextStep.classList.add('active');
    }
  },

  updateUploadModalError(msg) {
    const textEl = document.getElementById('upload-modal-status-text');
    if (textEl) {
      textEl.innerText = `Error: ${msg}`;
      textEl.style.color = 'var(--danger)';
    }
  },

  closeUploadModal() {
    const modal = document.getElementById('upload-progress-modal');
    if (modal) modal.classList.remove('active');
    for (let i = 1; i <= 6; i++) {
      const step = document.getElementById(`upload-step-${i}`);
      if (step) {
        step.className = 'stage-step';
        step.querySelector('.stage-icon').innerHTML = i;
      }
    }
  },

  // ----------------- Document Selection -----------------
  toggleDocSelection(docId) {
    if (this.state.selectedDocIds.has(docId)) {
      this.state.selectedDocIds.delete(docId);
    } else {
      this.state.selectedDocIds.add(docId);
    }
    this.updateSelectedDocPill();
  },

  async deleteDocument(docId) {
    if (!confirm('Are you sure you want to delete this document and its indexed vectors?')) return;
    try {
      await API.deleteDocument(docId);
      this.state.selectedDocIds.delete(docId);
      await this.loadDocuments();
      await this.loadDashboardStats();
    } catch (err) {
      alert(`Error deleting document: ${err.message}`);
    }
  },

  toggleChaptersList(docId) {
    const el = document.getElementById(`chapters-list-${docId}`);
    if (el) el.classList.toggle('open');
  },

  filterByChapter(chapterTitle) {
    this.state.selectedChapter = chapterTitle;
    const input = document.getElementById('chat-input-textarea');
    if (input) {
      input.value = `What does "${chapterTitle}" discuss?`;
      input.focus();
    }
  },

  // ----------------- Chat Execution -----------------
  async handleSendMessage(overrideQuestion = '') {
    const input = document.getElementById('chat-input-textarea');
    const question = (overrideQuestion || (input ? input.value : '')).trim();

    if (!question || this.state.isLoading) return;

    if (input && !overrideQuestion) {
      input.value = '';
      input.style.height = 'auto';
    }

    this.state.lastQuestion = question;
    this.state.isLoading = true;
    this.toggleSendBtn(true);

    this.hideDashboard();

    // 1. Append User Message
    this.appendMessage({
      role: 'user',
      content: question
    });

    // 2. Append Assistant Loading Bubble
    const loadingId = this.appendLoadingIndicator();

    try {
      // 3. Call RAG Endpoint with explicitly selected style
      const docIdsArray = Array.from(this.state.selectedDocIds);
      const res = await API.askQuestion({
        conversation_id: this.state.currentConvId,
        question: question,
        doc_ids: docIdsArray.length > 0 ? docIdsArray : null,
        chapter: this.state.selectedChapter,
        style: this.state.currentStyle
      });

      if (!this.state.currentConvId) {
        this.state.currentConvId = res.conversation_id;
        await this.loadConversations();
      }

      this.removeElement(loadingId);

      // 4. Append Assistant Response
      this.appendMessage({
        id: res.assistant_message.id,
        role: 'assistant',
        content: res.answer,
        confidence: res.confidence,
        style: this.state.currentStyle,
        sources: res.sources
      });

      // 5. Update Inspector Sources Tab
      this.updateSourcesInspection(res.sources);

      // 6. Refresh Stats
      await this.loadDashboardStats();

    } catch (err) {
      this.removeElement(loadingId);
      this.appendMessage({
        role: 'assistant',
        content: `**Error:** ${err.message || 'Failed to generate answer. Please try again.'}`,
        confidence: 'Low',
        style: this.state.currentStyle
      });
    } finally {
      this.state.isLoading = false;
      this.toggleSendBtn(false);
      this.scrollToBottom();
    }
  },

  appendMessage(msg) {
    const container = document.getElementById('chat-messages-container');
    if (!container) return;

    const isUser = msg.role === 'user';
    const row = document.createElement('div');
    row.className = `message-row ${isUser ? 'user' : 'assistant'}`;

    if (isUser) {
      row.innerHTML = `
        <div class="avatar user">👤</div>
        <div class="message-bubble">
          <div class="message-card">
            ${msg.content}
          </div>
        </div>
      `;
    } else {
      const confClass = (msg.confidence || 'high').toLowerCase();
      const sources = msg.sources || [];

      row.innerHTML = `
        <div class="avatar assistant">✨</div>
        <div class="message-bubble">
          <div class="message-card">
            <div class="message-header-bar">
              <div class="meta-badges">
                ${msg.style ? `<span class="badge-style">🎯 ${msg.style}</span>` : ''}
                <span class="badge-confidence ${confClass}">Confidence: ${msg.confidence || 'High'}</span>
              </div>
            </div>

            <div class="markdown-body">
              ${Chat.renderMarkdown(msg.content)}
            </div>

            ${sources.length > 0 ? `
              <div class="sources-bar">
                <div class="sources-label">Sources & Grounding Citations:</div>
                <div class="source-chips">
                  ${sources.map(s => `
                    <div class="source-chip" onclick="PDFViewer.openDocumentPage('${s.doc_id}', '${s.filename}', ${s.page})" title="View cited page in PDF reader">
                      <span>📄</span>
                      <span>${s.filename} (p.${s.page})</span>
                      <span class="source-score">${s.score}%</span>
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : ''}

            <div class="message-actions-bar">
              <button class="btn-msg-action" onclick="Chat.copyToClipboard(\`${this.escapeBackticks(msg.content)}\`, this)">
                <span>📋</span> Copy
              </button>
              <button class="btn-msg-action" onclick="Chat.toggleReadAloud(\`${this.escapeBackticks(msg.content)}\`, this)">
                <span>🔊</span> Read Aloud
              </button>
              <button class="btn-msg-action" onclick="App.regenerateLastQuestion()">
                <span>🔄</span> Regenerate
              </button>
              <button class="btn-msg-action" onclick="Chat.giveFeedback(this, 'up')">👍</button>
              <button class="btn-msg-action" onclick="Chat.giveFeedback(this, 'down')">👎</button>
            </div>
          </div>
        </div>
      `;
    }

    container.appendChild(row);
    this.scrollToBottom();
  },

  appendLoadingIndicator() {
    const container = document.getElementById('chat-messages-container');
    if (!container) return null;

    const id = `loading-${Date.now()}`;
    const row = document.createElement('div');
    row.id = id;
    row.className = 'message-row assistant';
    row.innerHTML = `
      <div class="avatar assistant">✨</div>
      <div class="message-bubble">
        <div class="message-card" style="display:flex; align-items:center; gap:12px; color:var(--text-muted); font-size:13px;">
          <div class="stage-icon spinner" style="width:20px; height:20px; border-width:2px; border-color:var(--accent-primary);"></div>
          <span>Retrieving grounded passages & formatting in <strong>${this.state.currentStyle}</strong> style...</span>
        </div>
      </div>
    `;
    container.appendChild(row);
    this.scrollToBottom();
    return id;
  },

  removeElement(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  },

  scrollToBottom() {
    const body = document.getElementById('chat-body');
    if (body) {
      body.scrollTop = body.scrollHeight;
    }
  },

  toggleSendBtn(disabled) {
    const btn = document.getElementById('btn-send-message');
    if (btn) btn.disabled = disabled;
  },

  regenerateLastQuestion() {
    if (this.state.lastQuestion) {
      this.handleSendMessage(this.state.lastQuestion);
    }
  },

  escapeBackticks(str) {
    return (str || '').replace(/`/g, '\\`').replace(/\$/g, '\\$');
  },

  // ----------------- Dashboard & Empty State -----------------
  renderDashboard() {
    const dashboard = document.getElementById('dashboard-view');
    const messages = document.getElementById('chat-messages-container');
    if (dashboard) dashboard.style.display = 'flex';
    if (messages) messages.innerHTML = '';
    this.renderSuggestedQuestions();
  },

  hideDashboard() {
    const dashboard = document.getElementById('dashboard-view');
    if (dashboard) dashboard.style.display = 'none';
  },

  renderSuggestedQuestions() {
    const container = document.getElementById('suggested-chips-container');
    if (!container) return;

    let questions = [];
    if (this.state.documents.length > 0) {
      this.state.documents.forEach(d => {
        if (d.suggested_questions && d.suggested_questions.length > 0) {
          questions.push(...d.suggested_questions);
        }
      });
    }

    if (questions.length === 0) {
      questions = [
        "What are the main concepts and principles discussed?",
        "Provide a comprehensive summary of key findings.",
        "What are the important definitions in this document?",
        "What are the practical applications or steps described?"
      ];
    }

    const unique = Array.from(new Set(questions)).slice(0, 6);
    container.innerHTML = unique.map(q => `
      <div class="suggested-chip" onclick="App.handleSendMessage('${this.escapeBackticks(q)}')">
        <span>💡</span> ${q}
      </div>
    `).join('');
  },

  // ----------------- Conversation Management -----------------
  async createNewChat() {
    try {
      const conv = await API.createConversation('New Conversation');
      this.state.conversations.unshift(conv);
      this.renderConversationList();
      await this.selectConversation(conv.id);
    } catch (err) {
      console.error('Failed to create conversation:', err);
    }
  },

  async selectConversation(convId) {
    this.state.currentConvId = convId;
    this.renderConversationList();

    const titleEl = document.getElementById('header-conv-title');
    const conv = this.state.conversations.find(c => c.id === convId);
    if (titleEl && conv) titleEl.innerText = conv.title;

    try {
      const res = await API.getConversation(convId);
      const messages = res.messages || [];

      if (messages.length === 0) {
        this.renderDashboard();
      } else {
        this.hideDashboard();
        const container = document.getElementById('chat-messages-container');
        if (container) container.innerHTML = '';

        messages.forEach(m => {
          this.appendMessage({
            id: m.id,
            role: m.role,
            content: m.content,
            confidence: m.confidence,
            style: m.style,
            sources: m.sources
          });
        });

        const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant');
        if (lastAssistant && lastAssistant.sources) {
          this.updateSourcesInspection(lastAssistant.sources);
        }
      }
    } catch (err) {
      console.error('Failed to load conversation messages:', err);
    }
  },

  async promptRenameConversation(convId, currentTitle) {
    const newTitle = prompt('Enter new conversation title:', currentTitle);
    if (newTitle && newTitle.trim()) {
      try {
        await API.renameConversation(convId, newTitle.trim());
        await this.loadConversations();
        const titleEl = document.getElementById('header-conv-title');
        if (titleEl && this.state.currentConvId === convId) {
          titleEl.innerText = newTitle.trim();
        }
      } catch (err) {
        alert('Failed to rename conversation');
      }
    }
  },

  async deleteConversation(convId) {
    if (!confirm('Are you sure you want to delete this chat?')) return;
    try {
      await API.deleteConversation(convId);
      this.state.conversations = this.state.conversations.filter(c => c.id !== convId);
      if (this.state.currentConvId === convId) {
        if (this.state.conversations.length > 0) {
          await this.selectConversation(this.state.conversations[0].id);
        } else {
          this.state.currentConvId = null;
          this.renderDashboard();
        }
      }
      this.renderConversationList();
    } catch (err) {
      alert('Failed to delete conversation');
    }
  },

  async clearCurrentChat() {
    if (!this.state.currentConvId) return;
    if (!confirm('Clear all messages in this conversation?')) return;
    try {
      await API.clearConversation(this.state.currentConvId);
      this.renderDashboard();
    } catch (err) {
      alert('Failed to clear conversation');
    }
  },

  // ----------------- Inspector: Sources -----------------
  updateSourcesInspection(sources) {
    const container = document.getElementById('inspector-sources-container');
    if (!container) return;

    if (!sources || sources.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding:35px 10px; color:var(--text-muted); font-size:12px;">
          Ask a question to see retrieved grounded source passages here.
        </div>
      `;
      return;
    }

    container.innerHTML = sources.map((s, idx) => `
      <div class="source-inspection-card">
        <div class="source-card-header">
          <div class="source-card-title" title="${s.filename}">📄 ${s.filename}</div>
          <span class="source-score">${s.score}% Match</span>
        </div>
        <div style="font-size:11px; color:var(--text-muted); font-weight:600;">
          Page ${s.page} • Chapter: ${s.chapter || 'General'}
        </div>
        <div class="source-card-text">
          "${s.text}"
        </div>
        <button class="btn-secondary" style="font-size:11px; padding:5px 10px; align-self:flex-start;" onclick="PDFViewer.openDocumentPage('${s.doc_id}', '${s.filename}', ${s.page})">
          🔍 Inspect Page ${s.page} in PDF Viewer
        </button>
      </div>
    `).join('');
  },

  // ----------------- Inspector: Smart Summarizer -----------------
  async handleGenerateSmartSummary() {
    const docSelect = document.getElementById('summarizer-doc-select');
    const chapterSelect = document.getElementById('summarizer-chapter-select');
    const modeSelect = document.getElementById('summarizer-mode-select');
    const lengthSelect = document.getElementById('summarizer-length-select');
    const outputCard = document.getElementById('summarizer-output-card');

    if (!docSelect || !docSelect.value) {
      alert('Please upload and select at least one document first.');
      return;
    }

    let docIds = [];
    if (docSelect.value === '__all__') {
      docIds = Array.from(this.state.selectedDocIds);
      if (docIds.length === 0) {
        docIds = this.state.documents.map(d => d.id);
      }
    } else {
      docIds = [docSelect.value];
    }

    const chapter = (chapterSelect && docSelect.value !== '__all__') ? chapterSelect.value : null;
    const mode = modeSelect ? modeSelect.value : 'detailed';
    const length = lengthSelect ? lengthSelect.value : 'detailed';

    if (outputCard) {
      outputCard.innerHTML = `
        <div style="display:flex; align-items:center; gap:10px; color:var(--text-muted); padding:25px 0; justify-content:center;">
          <div class="stage-icon spinner" style="width:22px; height:22px; border-color:var(--accent-primary);"></div>
          <span>Synthesizing smart ${mode.replace('_', ' ')} summary from documents...</span>
        </div>
      `;
    }

    try {
      const res = await API.generateSmartSummary({
        doc_ids: docIds,
        mode: mode,
        length: length,
        chapter: chapter
      });

      this.state.currentSmartSummary = {
        text: res.summary || '',
        docNames: res.doc_names || []
      };

      if (outputCard) {
        const modeLabel = mode.replace('_', ' ').toUpperCase();
        outputCard.innerHTML = `
          <div class="summary-actions-bar">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="node-category-badge root">✨ ${modeLabel}</span>
              <span style="font-size:11px; color:var(--text-muted); font-weight:600;">${res.chunks_analyzed || 0} excerpts analyzed</span>
            </div>
            <div style="display:flex; gap:6px;">
              <button class="btn-icon-xs" title="Copy Summary" onclick="Chat.copyToClipboard(\`${this.escapeBackticks(res.summary)}\`, this)">📋 Copy</button>
              <button class="btn-icon-xs" title="Download Summary as Markdown" onclick="App.downloadSmartSummary()">⬇️ Download</button>
            </div>
          </div>
          <div class="markdown-body" style="font-size:13px; line-height:1.65;">
            ${Chat.renderMarkdown(res.summary)}
          </div>
        `;
      }
    } catch (err) {
      if (outputCard) {
        outputCard.innerHTML = `<div style="color:var(--danger); padding:10px; font-size:12px;">Error generating summary: ${err.message}</div>`;
      }
    }
  },

  handleGenerateSummary() {
    return this.handleGenerateSmartSummary();
  },

  downloadSmartSummary() {
    const summary = this.state.currentSmartSummary.text;
    if (!summary) return;
    const blob = new Blob([summary], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `DocuMind_Summary_${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  // =========================================================
  // AI CONCEPT MAP GENERATOR
  // =========================================================
  async handleGenerateConceptMap() {
    const docSelect = document.getElementById('concept-map-doc-select');
    const topicInput = document.getElementById('concept-map-topic-input');
    const viewport = document.getElementById('concept-map-viewport');
    const toolbar = document.getElementById('concept-map-toolbar');
    const detailsBox = document.getElementById('concept-node-details');

    if (!docSelect || !docSelect.value) {
      alert('Please upload and select at least one document first.');
      return;
    }

    let docIds = [];
    if (docSelect.value === '__all__') {
      docIds = Array.from(this.state.selectedDocIds);
      if (docIds.length === 0) {
        docIds = this.state.documents.map(d => d.id);
      }
    } else {
      docIds = [docSelect.value];
    }

    const topic = topicInput ? topicInput.value.trim() : '';

    if (viewport) {
      viewport.innerHTML = `
        <div style="display:flex; flex-direction:column; align-items:center; gap:10px; color:var(--text-muted); padding:30px;">
          <div class="stage-icon spinner" style="width:26px; height:26px; border-color:var(--accent-primary);"></div>
          <span style="font-size:12px; font-weight:600;">Extracting concepts and relationships from document content...</span>
        </div>
      `;
    }
    if (detailsBox) detailsBox.style.display = 'none';

    try {
      const res = await API.generateConceptMap(docIds, topic);
      if (!res.nodes || res.nodes.length === 0) {
        if (viewport) {
          viewport.innerHTML = `<div style="color:var(--danger); font-size:12px; padding:20px;">Could not extract concept map from the selected content.</div>`;
        }
        return;
      }

      this.state.currentConceptMap = {
        data: res,
        zoom: 1.0,
        selectedNodeId: null
      };

      if (toolbar) toolbar.style.display = 'flex';
      const badge = document.getElementById('concept-map-title-badge');
      if (badge) badge.innerText = `🧠 ${res.main_topic || 'Concept Map'}`;

      this.renderConceptMap(res);

    } catch (err) {
      if (viewport) {
        viewport.innerHTML = `<div style="color:var(--danger); font-size:12px; padding:20px;">Error generating concept map: ${err.message}</div>`;
      }
    }
  },

  renderConceptMap(data) {
    const viewport = document.getElementById('concept-map-viewport');
    if (!viewport) return;

    const nodes = data.nodes || [];
    const edges = data.edges || [];

    if (nodes.length === 0) return;

    const width = 680;
    const height = 440;
    const centerX = width / 2;
    const centerY = height / 2;

    const rootNode = nodes.find(n => n.category === 'root') || nodes[0];
    const subtopics = nodes.filter(n => n.id !== rootNode.id && n.category === 'subtopic');
    const otherNodes = nodes.filter(n => n.id !== rootNode.id && n.category !== 'subtopic');

    const positions = {};
    positions[rootNode.id] = { x: centerX, y: centerY };

    const subtopicRadius = 130;
    subtopics.forEach((st, idx) => {
      const angle = (idx / Math.max(subtopics.length, 1)) * 2 * Math.PI - (Math.PI / 2);
      positions[st.id] = {
        x: centerX + subtopicRadius * Math.cos(angle),
        y: centerY + subtopicRadius * Math.sin(angle)
      };
    });

    const outerRadius = 195;
    otherNodes.forEach((node, idx) => {
      const edgeTo = edges.find(e => e.target === node.id);
      const parentPos = edgeTo && positions[edgeTo.source] ? positions[edgeTo.source] : null;

      if (parentPos && parentPos !== positions[rootNode.id]) {
        const dx = parentPos.x - centerX;
        const dy = parentPos.y - centerY;
        const angle = Math.atan2(dy, dx) + ((idx % 3) - 1) * 0.45;
        positions[node.id] = {
          x: Math.min(width - 55, Math.max(55, centerX + outerRadius * Math.cos(angle))),
          y: Math.min(height - 40, Math.max(40, centerY + outerRadius * Math.sin(angle)))
        };
      } else {
        const angle = (idx / Math.max(otherNodes.length, 1)) * 2 * Math.PI;
        positions[node.id] = {
          x: Math.min(width - 55, Math.max(55, centerX + outerRadius * Math.cos(angle))),
          y: Math.min(height - 40, Math.max(40, centerY + outerRadius * Math.sin(angle)))
        };
      }
    });

    let svgContent = `
      <svg class="concept-map-svg" id="concept-map-svg-el" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="rootGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#9333ea" />
            <stop offset="100%" stop-color="#ec4899" />
          </linearGradient>
          <linearGradient id="subtopicGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#2563eb" />
            <stop offset="100%" stop-color="#3b82f6" />
          </linearGradient>
          <linearGradient id="conceptGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#059669" />
            <stop offset="100%" stop-color="#10b981" />
          </linearGradient>
          <linearGradient id="methodGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#d97706" />
            <stop offset="100%" stop-color="#f59e0b" />
          </linearGradient>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        <g id="concept-map-edges">
    `;

    edges.forEach(edge => {
      const src = positions[edge.source];
      const tgt = positions[edge.target];
      if (!src || !tgt) return;

      const midX = (src.x + tgt.x) / 2;
      const midY = (src.y + tgt.y) / 2;
      const qx = midX + (src.y - tgt.y) * 0.12;
      const qy = midY + (tgt.x - src.x) * 0.12;

      svgContent += `
        <g class="concept-edge-group">
          <path d="M ${src.x} ${src.y} Q ${qx} ${qy} ${tgt.x} ${tgt.y}" class="concept-edge" />
          ${edge.label ? `
            <text x="${qx}" y="${qy}" class="concept-edge-label">${edge.label}</text>
          ` : ''}
        </g>
      `;
    });

    svgContent += `</g><g id="concept-map-nodes">`;

    nodes.forEach(node => {
      const pos = positions[node.id] || { x: centerX, y: centerY };
      const isRoot = node.id === rootNode.id;
      const cat = node.category || 'concept';

      let fill = 'url(#conceptGrad)';
      let rx = 16;
      let boxW = Math.max(90, Math.min(150, node.label.length * 8.5 + 24));
      let boxH = isRoot ? 40 : 32;

      if (isRoot) {
        fill = 'url(#rootGrad)';
        boxW = Math.max(120, Math.min(180, node.label.length * 9 + 30));
      } else if (cat === 'subtopic') {
        fill = 'url(#subtopicGrad)';
      } else if (cat === 'method') {
        fill = 'url(#methodGrad)';
      }

      svgContent += `
        <g class="concept-node-group" id="svg-node-${node.id}" onclick="App.selectConceptNode('${node.id}')" transform="translate(${pos.x}, ${pos.y})">
          <rect 
            x="${-boxW / 2}" 
            y="${-boxH / 2}" 
            width="${boxW}" 
            height="${boxH}" 
            rx="${rx}" 
            fill="${fill}" 
            stroke="rgba(255, 255, 255, 0.45)" 
            stroke-width="1.5" 
            class="node-rect"
            filter="${isRoot ? 'url(#glow)' : 'none'}" />
          <text 
            text-anchor="middle" 
            dy="4" 
            fill="#ffffff" 
            font-size="${isRoot ? 12 : 11}" 
            font-weight="700" 
            font-family="'Inter', sans-serif">
            ${node.label.length > 20 ? node.label.slice(0, 18) + '...' : node.label}
          </text>
        </g>
      `;
    });

    svgContent += `</g></svg>`;

    viewport.innerHTML = svgContent;
    this.selectConceptNode(rootNode.id);
  },

  selectConceptNode(nodeId) {
    const data = this.state.currentConceptMap.data;
    if (!data || !data.nodes) return;

    const node = data.nodes.find(n => n.id === nodeId);
    if (!node) return;

    this.state.currentConceptMap.selectedNodeId = nodeId;

    document.querySelectorAll('.concept-node-group').forEach(el => el.classList.remove('active'));
    const activeEl = document.getElementById(`svg-node-${nodeId}`);
    if (activeEl) activeEl.classList.add('active');

    const relatedEdges = (data.edges || []).filter(e => e.source === nodeId || e.target === nodeId);
    const relatedNames = relatedEdges.map(e => {
      const otherId = e.source === nodeId ? e.target : e.source;
      const otherNode = data.nodes.find(n => n.id === otherId);
      const direction = e.source === nodeId ? '→' : '←';
      return otherNode ? `${direction} <strong>${e.label || 'connected to'}</strong>: <em>${otherNode.label}</em>` : '';
    }).filter(Boolean);

    const doc = this.state.documents.find(d => d.filename === node.source_doc) || this.state.documents[0];
    const docId = doc ? doc.id : '';

    const detailsBox = document.getElementById('concept-node-details');
    if (detailsBox) {
      detailsBox.style.display = 'block';
      detailsBox.innerHTML = `
        <div class="node-details-card">
          <div class="node-details-header">
            <span style="font-size:14px; font-weight:800; color:var(--text-primary);">💡 ${node.label}</span>
            <span class="node-category-badge ${node.category || 'concept'}">${(node.category || 'Concept').toUpperCase()}</span>
          </div>

          <div style="font-size:12px; line-height:1.6; color:var(--text-secondary); margin-top:2px;">
            ${node.explanation}
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px; padding-top:6px; border-top:1px solid var(--border-color); font-size:11px;">
            <div style="color:var(--text-muted); font-weight:600;">
              📄 ${node.source_doc || 'Document'} • Page ${node.source_page || 1}
            </div>
            ${docId ? `
              <button class="btn-secondary" style="font-size:11px; padding:3px 8px;" onclick="PDFViewer.openDocumentPage('${docId}', '${node.source_doc}', ${node.source_page || 1})">
                🔍 Open Page ${node.source_page || 1}
              </button>
            ` : ''}
          </div>

          ${relatedNames.length > 0 ? `
            <div style="margin-top:4px; font-size:11px; color:var(--text-muted);">
              <strong>Key Relations:</strong>
              <div style="display:flex; flex-direction:column; gap:2px; margin-top:2px; font-size:11px;">
                ${relatedNames.slice(0, 4).map(r => `<div>${r}</div>`).join('')}
              </div>
            </div>
          ` : ''}
        </div>
      `;
    }
  },

  zoomConceptMap(factor) {
    const svg = document.getElementById('concept-map-svg-el');
    if (!svg) return;
    this.state.currentConceptMap.zoom = Math.min(2.5, Math.max(0.4, this.state.currentConceptMap.zoom * factor));
    svg.style.transform = `scale(${this.state.currentConceptMap.zoom})`;
  },

  resetConceptMapZoom() {
    const svg = document.getElementById('concept-map-svg-el');
    if (!svg) return;
    this.state.currentConceptMap.zoom = 1.0;
    svg.style.transform = `scale(1.0)`;
  },

  copyConceptMap(btn) {
    const data = this.state.currentConceptMap.data;
    if (!data || !data.nodes || data.nodes.length === 0) {
      alert('Please generate a concept map first.');
      return;
    }

    let md = `# 🧠 Concept Map: ${data.main_topic || 'Overview'}\n\n`;
    if (data.summary) {
      md += `${data.summary}\n\n`;
    }
    md += `## 📚 Key Concepts:\n`;
    data.nodes.forEach(n => {
      md += `- **${n.label}** [${(n.category || 'concept').toUpperCase()}]: ${n.explanation} \`[${n.source_doc || 'Document'}, p.${n.source_page || 1}]\`\n`;
    });

    if (data.edges && data.edges.length > 0) {
      md += `\n## 🔗 Semantic Relationships:\n`;
      data.edges.forEach(e => {
        const srcNode = data.nodes.find(n => n.id === e.source);
        const tgtNode = data.nodes.find(n => n.id === e.target);
        if (srcNode && tgtNode) {
          md += `- **${srcNode.label}** --[${e.label || 'relates to'}]--> **${tgtNode.label}**\n`;
        }
      });
    }

    Chat.copyToClipboard(md, btn);
  },

  downloadConceptMap() {
    const data = this.state.currentConceptMap.data;
    if (!data || !data.nodes || data.nodes.length === 0) {
      alert('Please generate a concept map first.');
      return;
    }

    const jsonStr = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `DocuMind_Concept_Map_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  exportConceptMapImage() {
    const svg = document.getElementById('concept-map-svg-el');
    if (!svg) return;

    try {
      const serializer = new XMLSerializer();
      let source = serializer.serializeToString(svg);

      if (!source.match(/^<svg[^>]+xmlns="http\:\/\/www\.w3\.org\/2000\/svg"/)) {
        source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
      }

      const svgBlob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);

      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = 1360;
        canvas.height = 880;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        canvas.toBlob((blob) => {
          if (blob) {
            const pngUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = pngUrl;
            a.download = `DocuMind_Concept_Map_${new Date().toISOString().slice(0, 10)}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(pngUrl);
          }
        }, 'image/png');
        URL.revokeObjectURL(url);
      };
      img.src = url;
    } catch (e) {
      const svgBlob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'DocuMind_Concept_Map.svg';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  },

  // =========================================================
  // INTERACTIVE QUIZ PLAYER
  // =========================================================
  async handleGenerateQuiz() {
    const docSelect = document.getElementById('quiz-doc-select');
    const chapterSelect = document.getElementById('quiz-chapter-select');
    const countSelect = document.getElementById('quiz-count-select');
    const diffSelect = document.getElementById('quiz-diff-select');
    const displayArea = document.getElementById('quiz-display-area');

    if (!docSelect || !docSelect.value) {
      alert('Please select an uploaded document.');
      return;
    }

    const docId = docSelect.value;
    const chapter = chapterSelect.value;
    const numQ = parseInt(countSelect.value, 10) || 5;
    const diff = diffSelect.value;

    displayArea.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px; color:var(--text-muted); padding:20px 0;">
        <div class="stage-icon spinner" style="width:20px; height:20px; border-color:var(--accent-primary);"></div>
        <span>Generating interactive quiz questions from document...</span>
      </div>
    `;

    try {
      const res = await API.generateQuiz(docId, {
        chapter: chapter,
        num_questions: numQ,
        difficulty: diff
      });

      if (!res.questions || res.questions.length === 0) {
        displayArea.innerHTML = `<div style="color:var(--danger); font-size:13px;">Could not generate questions for this document.</div>`;
        return;
      }

      this.state.currentQuiz = {
        questions: res.questions,
        currentIndex: 0,
        score: 0,
        answered: false
      };

      this.renderCurrentQuizQuestion();

    } catch (err) {
      displayArea.innerHTML = `<div style="color:var(--danger); font-size:13px;">Error: ${err.message}</div>`;
    }
  },

  renderCurrentQuizQuestion() {
    const displayArea = document.getElementById('quiz-display-area');
    const qState = this.state.currentQuiz;
    const q = qState.questions[qState.currentIndex];

    if (!q) {
      this.renderQuizResults();
      return;
    }

    qState.answered = false;

    displayArea.innerHTML = `
      <div class="quiz-card">
        <div class="quiz-header-bar">
          <span>Question ${qState.currentIndex + 1} of ${qState.questions.length}</span>
          <span class="quiz-score-badge">Score: ${qState.score}</span>
        </div>

        <div class="quiz-question-text">
          ${q.question}
        </div>

        <div class="quiz-options-list" id="quiz-options-container">
          ${q.options.map((opt, idx) => `
            <button class="quiz-option-btn" onclick="App.handleQuizAnswer(${idx})">
              <span>${opt}</span>
            </button>
          `).join('')}
        </div>

        <div id="quiz-feedback-box" style="display:none;"></div>

        <button id="btn-quiz-next" class="btn-action-primary" style="display:none; margin-top:8px;" onclick="App.nextQuizQuestion()">
          Next Question ➡️
        </button>
      </div>
    `;
  },

  handleQuizAnswer(selectedIndex) {
    const qState = this.state.currentQuiz;
    if (qState.answered) return;
    qState.answered = true;

    const q = qState.questions[qState.currentIndex];
    const isCorrect = selectedIndex === q.correct_index;
    if (isCorrect) qState.score++;

    const buttons = document.querySelectorAll('#quiz-options-container .quiz-option-btn');
    buttons.forEach((btn, idx) => {
      btn.style.pointerEvents = 'none';
      if (idx === q.correct_index) {
        btn.classList.add('correct');
        btn.innerHTML += ' <span>✓</span>';
      } else if (idx === selectedIndex) {
        btn.classList.add('incorrect');
        btn.innerHTML += ' <span>✕</span>';
      }
    });

    const feedbackBox = document.getElementById('quiz-feedback-box');
    if (feedbackBox) {
      feedbackBox.style.display = 'block';
      feedbackBox.className = 'quiz-explanation-box';
      feedbackBox.innerHTML = `
        <div style="font-weight:700; color:${isCorrect ? 'var(--success)' : 'var(--danger)'}; margin-bottom:4px;">
          ${isCorrect ? '🎉 Correct Answer!' : '❌ Incorrect'}
        </div>
        <div>${q.explanation || ''}</div>
        <div style="font-size:11px; color:var(--text-muted); margin-top:6px;">📖 Source: ${q.source || 'Uploaded Document'}</div>
      `;
    }

    const nextBtn = document.getElementById('btn-quiz-next');
    if (nextBtn) nextBtn.style.display = 'flex';
  },

  nextQuizQuestion() {
    this.state.currentQuiz.currentIndex++;
    this.renderCurrentQuizQuestion();
  },

  renderQuizResults() {
    const displayArea = document.getElementById('quiz-display-area');
    const qState = this.state.currentQuiz;
    const total = qState.questions.length;
    const pct = Math.round((qState.score / total) * 100);

    displayArea.innerHTML = `
      <div class="quiz-card" style="text-align:center; padding:24px;">
        <div style="font-size:36px; margin-bottom:8px;">🏆</div>
        <div style="font-size:18px; font-weight:800; color:var(--text-primary); margin-bottom:4px;">Quiz Completed!</div>
        <div style="font-size:13px; color:var(--text-secondary); margin-bottom:16px;">
          You scored <strong style="color:var(--accent-primary); font-size:16px;">${qState.score}</strong> out of <strong>${total}</strong> (${pct}%)
        </div>

        <div style="display:flex; gap:10px;">
          <button class="btn-secondary" style="flex:1;" onclick="App.retakeQuiz()">
            🔄 Retake Quiz
          </button>
          <button class="btn-action-primary" style="flex:1;" onclick="App.handleGenerateQuiz()">
            ✨ New Quiz
          </button>
        </div>
      </div>
    `;
  },

  retakeQuiz() {
    this.state.currentQuiz.currentIndex = 0;
    this.state.currentQuiz.score = 0;
    this.renderCurrentQuizQuestion();
  },

  // =========================================================
  // STUDY FLASHCARDS (3D FLIP ANIMATION)
  // =========================================================
  async handleGenerateFlashcards() {
    const docSelect = document.getElementById('flashcard-doc-select');
    const chapterSelect = document.getElementById('flashcard-chapter-select');
    const countSelect = document.getElementById('flashcard-count-select');
    const displayArea = document.getElementById('flashcard-display-area');

    if (!docSelect || !docSelect.value) {
      alert('Please select an uploaded document.');
      return;
    }

    const docId = docSelect.value;
    const chapter = chapterSelect.value;
    const numCards = parseInt(countSelect.value, 10) || 8;

    displayArea.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px; color:var(--text-muted); padding:20px 0;">
        <div class="stage-icon spinner" style="width:20px; height:20px; border-color:var(--accent-primary);"></div>
        <span>Generating study flashcards with 3D animation...</span>
      </div>
    `;

    try {
      const res = await API.generateFlashcards(docId, {
        chapter: chapter,
        num_cards: numCards
      });

      if (!res.flashcards || res.flashcards.length === 0) {
        displayArea.innerHTML = `<div style="color:var(--danger); font-size:13px;">No flashcards could be generated from this document.</div>`;
        return;
      }

      this.state.currentFlashcards = {
        cards: res.flashcards,
        currentIndex: 0,
        isFlipped: false,
        mastered: new Set()
      };

      this.renderCurrentFlashcard();

    } catch (err) {
      displayArea.innerHTML = `<div style="color:var(--danger); font-size:13px;">Error: ${err.message}</div>`;
    }
  },

  renderCurrentFlashcard() {
    const displayArea = document.getElementById('flashcard-display-area');
    const fState = this.state.currentFlashcards;
    const card = fState.cards[fState.currentIndex];

    if (!card) return;

    const total = fState.cards.length;
    const progressPct = Math.round(((fState.currentIndex + 1) / total) * 100);
    const isMastered = fState.mastered.has(card.id);

    displayArea.innerHTML = `
      <div class="flashcards-deck">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; font-size:12px; font-weight:700; color:var(--text-muted);">
          <span>Card ${fState.currentIndex + 1} of ${total}</span>
          <span style="color:var(--accent-primary);">⭐ Mastered: ${fState.mastered.size}</span>
        </div>

        <div class="flashcard-progress-bar" style="margin-bottom:12px;">
          <div class="flashcard-progress-fill" style="width:${progressPct}%;"></div>
        </div>

        <div class="flashcard-wrapper ${fState.isFlipped ? 'flipped' : ''}" id="flashcard-active-card" onclick="App.toggleFlipFlashcard()">
          <div class="flashcard-inner">
            <!-- Front -->
            <div class="flashcard-front">
              <span class="flashcard-category-badge">${card.category || 'Concept'}</span>
              <div class="flashcard-main-text">${card.front}</div>
              <div class="flashcard-hint">🔄 Click anywhere to reveal answer</div>
            </div>

            <!-- Back -->
            <div class="flashcard-back">
              <span class="flashcard-category-badge" style="background:rgba(16,185,129,0.15); color:var(--success);">Explanation & Definition</span>
              <div class="flashcard-main-text" style="font-size:14px; font-weight:500;">${card.back}</div>
              <div style="display:flex; justify-content:space-between; width:100%; font-size:11px; color:var(--text-muted);">
                <span>📖 ${card.source || ''}</span>
                <span class="flashcard-hint">🔄 Click to flip</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Controls -->
        <div class="flashcard-controls" style="margin-top:14px;">
          <button class="btn-secondary" style="padding:8px 12px;" onclick="App.prevFlashcard()" ${fState.currentIndex === 0 ? 'disabled' : ''}>
            ◀ Prev
          </button>
          <button class="btn-secondary" style="padding:8px 12px;" onclick="App.toggleMasteredFlashcard(${card.id})">
            ${isMastered ? '⭐ Mastered' : '☆ Mark Learned'}
          </button>
          <button class="btn-secondary" style="padding:8px 12px;" onclick="App.toggleFlipFlashcard()">
            🔄 Flip
          </button>
          <button class="btn-action-primary" style="padding:8px 16px; width:auto;" onclick="App.nextFlashcard()" ${fState.currentIndex === total - 1 ? 'disabled' : ''}>
            Next ▶
          </button>
        </div>
      </div>
    `;
  },

  toggleFlipFlashcard() {
    this.state.currentFlashcards.isFlipped = !this.state.currentFlashcards.isFlipped;
    const cardEl = document.getElementById('flashcard-active-card');
    if (cardEl) {
      cardEl.classList.toggle('flipped', this.state.currentFlashcards.isFlipped);
    }
  },

  nextFlashcard() {
    const fState = this.state.currentFlashcards;
    if (fState.currentIndex < fState.cards.length - 1) {
      fState.currentIndex++;
      fState.isFlipped = false;
      this.renderCurrentFlashcard();
    }
  },

  prevFlashcard() {
    const fState = this.state.currentFlashcards;
    if (fState.currentIndex > 0) {
      fState.currentIndex--;
      fState.isFlipped = false;
      this.renderCurrentFlashcard();
    }
  },

  toggleMasteredFlashcard(cardId) {
    const fState = this.state.currentFlashcards;
    if (fState.mastered.has(cardId)) {
      fState.mastered.delete(cardId);
    } else {
      fState.mastered.add(cardId);
    }
    this.renderCurrentFlashcard();
  },

  // ----------------- Settings Modal -----------------
  openSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (!modal) return;

    const providerSelect = document.getElementById('settings-provider-select');
    const geminiInput = document.getElementById('settings-gemini-key');
    const openaiInput = document.getElementById('settings-openai-key');
    const groqInput = document.getElementById('settings-groq-key');

    if (providerSelect) providerSelect.value = this.state.settings.active_provider || 'gemini';
    if (geminiInput) geminiInput.placeholder = this.state.settings.gemini_key_masked || 'Enter Gemini API Key';
    if (openaiInput) openaiInput.placeholder = this.state.settings.openai_key_masked || 'Enter OpenAI API Key';
    if (groqInput) groqInput.placeholder = this.state.settings.groq_key_masked || 'Enter Groq API Key';

    modal.classList.add('active');
  },

  closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.remove('active');
  },

  async saveSettings() {
    const provider = document.getElementById('settings-provider-select').value;
    const geminiKey = document.getElementById('settings-gemini-key').value;
    const openaiKey = document.getElementById('settings-openai-key').value;
    const groqKey = document.getElementById('settings-groq-key').value;

    const payload = { active_provider: provider };
    if (geminiKey.trim()) payload.gemini_api_key = geminiKey.trim();
    if (openaiKey.trim()) payload.openai_api_key = openaiKey.trim();
    if (groqKey.trim()) payload.groq_api_key = groqKey.trim();

    try {
      await API.updateSettings(payload);
      await this.loadSettings();
      this.closeSettingsModal();
      alert('Settings updated successfully!');
    } catch (err) {
      alert(`Failed to save settings: ${err.message}`);
    }
  },

  async testCurrentProvider() {
    const provider = document.getElementById('settings-provider-select').value;
    let key = '';
    if (provider === 'gemini') key = document.getElementById('settings-gemini-key').value;
    if (provider === 'openai') key = document.getElementById('settings-openai-key').value;
    if (provider === 'groq') key = document.getElementById('settings-groq-key').value;

    const resultEl = document.getElementById('settings-test-result');
    if (resultEl) {
      resultEl.innerText = 'Testing connection...';
      resultEl.style.color = 'var(--text-muted)';
    }

    try {
      const res = await API.testProvider(provider, key);
      if (resultEl) {
        resultEl.innerText = res.message;
        resultEl.style.color = res.status === 'success' ? 'var(--success)' : 'var(--danger)';
      }
    } catch (err) {
      if (resultEl) {
        resultEl.innerText = `Error: ${err.message}`;
        resultEl.style.color = 'var(--danger)';
      }
    }
  }
};

// Start application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
