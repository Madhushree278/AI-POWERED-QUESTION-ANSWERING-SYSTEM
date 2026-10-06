// API Client for DocuMind AI
const API = {
  baseUrl: '',

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    try {
      const response = await fetch(url, options);
      if (!response.ok) {
        let errorMsg = `Server error: ${response.statusText}`;
        try {
          const errData = await response.json();
          if (errData.detail) errorMsg = errData.detail;
        } catch (_) {}
        throw new Error(errorMsg);
      }
      return await response.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  // Document management
  async uploadDocuments(files) {
    const formData = new FormData();
    for (const file of files) {
      formData.append('files', file);
    }
    return await this.request('/api/documents/upload', {
      method: 'POST',
      body: formData
    });
  },

  async getDocuments(search = '') {
    const query = search ? `?search=${encodeURIComponent(search)}` : '';
    return await this.request(`/api/documents${query}`);
  },

  async getDocument(docId) {
    return await this.request(`/api/documents/${docId}`);
  },

  async deleteDocument(docId) {
    return await this.request(`/api/documents/${docId}`, {
      method: 'DELETE'
    });
  },

  getPageImageUrl(docId, pageNum) {
    return `/api/documents/${docId}/page/${pageNum}/image`;
  },

  // Chat & RAG
  async askQuestion(payload) {
    return await this.request('/api/chat/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  },

  // Summarization
  async summarizeDocument(docId, payload) {
    return await this.request(`/api/documents/${docId}/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  },

  // Interactive Quiz
  async generateQuiz(docId, payload) {
    return await this.request(`/api/documents/${docId}/quiz`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  },

  // Study Flashcards
  async generateFlashcards(docId, payload) {
    return await this.request(`/api/documents/${docId}/flashcards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  },

  // Conversations
  async getConversations() {
    return await this.request('/api/conversations');
  },

  async createConversation(title = 'New Conversation') {
    return await this.request('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title })
    });
  },

  async getConversation(convId) {
    return await this.request(`/api/conversations/${convId}`);
  },

  async renameConversation(convId, title) {
    return await this.request(`/api/conversations/${convId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title })
    });
  },

  async deleteConversation(convId) {
    return await this.request(`/api/conversations/${convId}`, {
      method: 'DELETE'
    });
  },

  async clearConversation(convId) {
    return await this.request(`/api/conversations/${convId}/clear`, {
      method: 'POST'
    });
  },

  // Settings & Dashboard
  async getSettings() {
    return await this.request('/api/settings');
  },

  async updateSettings(settings) {
    return await this.request('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings)
    });
  },

  async testProvider(provider, apiKey = '', model = '') {
    return await this.request('/api/settings/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, api_key: apiKey, model })
    });
  },

  async getDashboardStats() {
    return await this.request('/api/dashboard/stats');
  }
};
