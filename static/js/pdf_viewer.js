// PDF & Document Viewer Controller
const PDFViewer = {
  currentDocId: null,
  currentFilename: null,
  currentPage: 1,
  totalPages: 1,
  currentZoom: 100,

  openDocumentPage(docId, filename, pageNum = 1, totalPages = 1) {
    this.currentDocId = docId;
    this.currentFilename = filename;
    this.currentPage = pageNum;
    this.totalPages = totalPages || 1;
    this.currentZoom = 100;

    // Switch right inspector to PDF Viewer tab
    const pdfTabBtn = document.querySelector('[data-inspector-tab="pdf"]');
    if (pdfTabBtn) pdfTabBtn.click();

    // Ensure right inspector is open
    const inspector = document.getElementById('inspector-panel');
    if (inspector && inspector.classList.contains('collapsed')) {
      inspector.classList.remove('collapsed');
    }

    this.renderCurrentPage();
  },

  openDocumentByNameAndPage(filename, pageNum = 1) {
    if (!filename) return;
    const cleanTarget = filename.trim().toLowerCase();
    const doc = (App.state.documents || []).find(d => 
      d.filename.toLowerCase() === cleanTarget || 
      d.filename.toLowerCase().includes(cleanTarget) ||
      cleanTarget.includes(d.filename.toLowerCase())
    ) || (App.state.documents && App.state.documents[0]);

    if (doc) {
      this.openDocumentPage(doc.id, doc.filename, pageNum, doc.page_count);
    }
  },

  renderCurrentPage() {
    if (!this.currentDocId) return;

    const displayContainer = document.getElementById('pdf-display-container');
    const titleEl = document.getElementById('pdf-doc-title');
    const pageNumInput = document.getElementById('pdf-page-input');
    const totalPagesEl = document.getElementById('pdf-total-pages');

    if (titleEl) titleEl.innerText = this.currentFilename || 'Document Viewer';
    if (pageNumInput) pageNumInput.value = this.currentPage;
    if (totalPagesEl) totalPagesEl.innerText = this.totalPages;

    if (!displayContainer) return;

    // Show loading spinner
    displayContainer.innerHTML = `
      <div style="display:flex; flex-direction:column; align-items:center; gap:10px; color:var(--text-muted);">
        <div class="stage-icon spinner" style="width:28px; height:28px; border-width:3px;"></div>
        <span>Rendering Page ${this.currentPage}...</span>
      </div>
    `;

    // Fetch page image
    const imgUrl = API.getPageImageUrl(this.currentDocId, this.currentPage);
    const img = new Image();
    img.src = `${imgUrl}?t=${Date.now()}`;
    img.className = 'pdf-page-img';
    img.style.transform = `scale(${this.currentZoom / 100})`;
    img.style.transformOrigin = 'center center';
    img.style.transition = 'transform 0.15s ease';

    img.onload = () => {
      displayContainer.innerHTML = '';
      displayContainer.appendChild(img);
    };

    img.onerror = () => {
      // Fallback for DOCX/TXT or rendering error
      displayContainer.innerHTML = `
        <div style="padding:24px; text-align:center; color:var(--text-secondary); max-width:300px;">
          <div style="font-size:32px; margin-bottom:8px;">📄</div>
          <div style="font-weight:600; margin-bottom:6px;">Page ${this.currentPage}</div>
          <div style="font-size:12px; color:var(--text-muted); line-height:1.5;">
            Non-PDF documents or text pages are accessible via the source citations and text extracts.
          </div>
        </div>
      `;
    };
  },

  nextPage() {
    if (this.currentPage < this.totalPages) {
      this.currentPage++;
      this.renderCurrentPage();
    }
  },

  prevPage() {
    if (this.currentPage > 1) {
      this.currentPage--;
      this.renderCurrentPage();
    }
  },

  jumpToPage(num) {
    const target = parseInt(num, 10);
    if (!isNaN(target) && target >= 1 && target <= this.totalPages) {
      this.currentPage = target;
      this.renderCurrentPage();
    }
  },

  zoomIn() {
    if (this.currentZoom < 200) {
      this.currentZoom += 20;
      this.applyZoom();
    }
  },

  zoomOut() {
    if (this.currentZoom > 60) {
      this.currentZoom -= 20;
      this.applyZoom();
    }
  },

  applyZoom() {
    const img = document.querySelector('.pdf-page-img');
    const zoomValEl = document.getElementById('pdf-zoom-val');
    if (img) img.style.transform = `scale(${this.currentZoom / 100})`;
    if (zoomValEl) zoomValEl.innerText = `${this.currentZoom}%`;
  }
};
