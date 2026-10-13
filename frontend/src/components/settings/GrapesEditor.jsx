import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import grapesjs from 'grapesjs';
import 'grapesjs/dist/css/grapes.min.css';
import newsletterPreset from 'grapesjs-preset-newsletter';
// Icons used by the newsletter preset panels (scoped to the editor chunk, which is lazy-loaded).
import '@fortawesome/fontawesome-free/css/fontawesome.min.css';
import '@fortawesome/fontawesome-free/css/solid.min.css';

/**
 * Ensure all <img> tags in exported HTML have max-width: 100% and height: auto
 * so they adapt cleanly to desktop, tablet, and mobile views.
 */
export const ensureResponsiveImages = (html) => {
  if (!html || !html.includes('<img')) return html;
  return html.replace(/<img\b([^>]*)>/gi, (match, attrs) => {
    if (/style\s*=\s*["'][^"']*max-width/i.test(attrs)) {
      return match;
    }
    if (/style\s*=\s*(["'])([^"']*)(\1)/i.test(attrs)) {
      return match.replace(/style\s*=\s*(["'])([^"']*)(\1)/i, 'style=$1max-width: 100%; height: auto; display: inline-block; $2$1');
    }
    return `<img style="max-width: 100%; height: auto; display: inline-block;" ${attrs}>`;
  });
};

/**
 * Isolated GrapesJS (newsletter preset) wrapper.
 * Parent controls it through ref: getData(), loadHtml(), isDirty(), markClean().
 * Nothing here touches Redux or global styles.
 */
const GrapesEditor = forwardRef(function GrapesEditor({ projectData, initialHtml, height = '640px', onDirty }, ref) {
  const containerRef = useRef(null);
  const editorRef = useRef(null);
  const dirtyRef = useRef(false);
  const changeCount = useRef(0);

  useEffect(() => {
    const editor = grapesjs.init({
      container: containerRef.current,
      height,
      width: 'auto',
      fromElement: false,
      storageManager: false,
      assetManager: { embedAsBase64: true, dropzone: true },
      plugins: [newsletterPreset],
      // Scripts in imported/pasted markup are never executed in the canvas.
      allowScripts: 0,
    });
    editorRef.current = editor;

    // Inject sidebar Block Manager styling for high-contrast visible Smart Tags
    const sidebarStyle = document.createElement('style');
    sidebarStyle.id = 'gjs-smart-tags-block-style';
    sidebarStyle.innerHTML = `
      .gjs-blocks-c .gjs-block {
        min-height: 84px !important;
        background: #182234 !important;
        border: 1px solid #334155 !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        cursor: grab !important;
        padding: 4px !important;
        box-sizing: border-box !important;
      }
      .gjs-blocks-c .gjs-block:hover {
        background: #1e293b !important;
        border-color: #6366f1 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 16px -2px rgba(99, 102, 241, 0.35) !important;
      }
      .gjs-blocks-c .gjs-block:active {
        cursor: grabbing !important;
        transform: scale(0.96) !important;
      }
      .gjs-block-category .gjs-title {
        font-weight: 800 !important;
        font-size: 11px !important;
        letter-spacing: 0.6px !important;
        color: #f8fafc !important;
        background: #0f172a !important;
        border-bottom: 1px solid #334155 !important;
        padding: 10px 14px !important;
        text-transform: uppercase !important;
      }
    `;
    if (!document.getElementById('gjs-smart-tags-block-style')) {
      document.head.appendChild(sidebarStyle);
    }

    // Configure crystal-clear, high-contrast Smart Tag blocks in GrapesJS Block Manager
    const personalBlocks = [
      {
        id: 'tag-contact-name',
        icon: '👤',
        name: 'Contact Name',
        tag: 'Recipient',
        accentColor: '#38bdf8',
        bgBadge: 'rgba(56, 189, 248, 0.2)',
        borderColor: 'rgba(56, 189, 248, 0.5)',
        content: '{{contact_name}}',
        title: "Inserts recipient's name ({{contact_name}})",
      },
      {
        id: 'tag-company-name',
        icon: '🏢',
        name: 'Company Name',
        tag: 'Company',
        accentColor: '#818cf8',
        bgBadge: 'rgba(129, 140, 248, 0.2)',
        borderColor: 'rgba(129, 140, 248, 0.5)',
        content: '{{company_name}}',
        title: "Inserts client's company name ({{company_name}})",
      },
      {
        id: 'tag-designation',
        icon: '💼',
        name: 'Job Title',
        tag: 'Role',
        accentColor: '#c084fc',
        bgBadge: 'rgba(192, 132, 252, 0.2)',
        borderColor: 'rgba(192, 132, 252, 0.5)',
        content: '{{designation}}',
        title: "Inserts recipient's job title ({{designation}})",
      },
      {
        id: 'tag-website',
        icon: '🌐',
        name: 'Company Website',
        tag: 'Website',
        accentColor: '#34d399',
        bgBadge: 'rgba(52, 211, 153, 0.2)',
        borderColor: 'rgba(52, 211, 153, 0.5)',
        content: '{{website}}',
        title: "Inserts company website ({{website}})",
      },
      {
        id: 'tag-sender-name',
        icon: '✍️',
        name: 'Your Name',
        tag: 'Sender Name',
        accentColor: '#fbbf24',
        bgBadge: 'rgba(251, 191, 36, 0.2)',
        borderColor: 'rgba(251, 191, 36, 0.5)',
        content: '{{sender_name}}',
        title: 'Inserts your sender name ({{sender_name}})',
      },
      {
        id: 'tag-sender-email',
        icon: '✉️',
        name: 'Your Email',
        tag: 'Sender Email',
        accentColor: '#fb7185',
        bgBadge: 'rgba(251, 113, 133, 0.2)',
        borderColor: 'rgba(251, 113, 133, 0.5)',
        content: '{{sender_email}}',
        title: 'Inserts your sender email ({{sender_email}})',
      },
    ];

    personalBlocks.forEach((b) => {
      editor.BlockManager.add(b.id, {
        label: `
          <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;height:100%;padding:6px 2px;box-sizing:border-box;text-align:center;user-select:none;">
            <div style="font-size:20px;line-height:1;margin-bottom:5px;filter:drop-shadow(0 2px 3px rgba(0,0,0,0.6));">${b.icon}</div>
            <div style="font-size:11px;font-weight:700;color:#ffffff;line-height:1.2;text-shadow:0 1px 2px rgba(0,0,0,0.9);letter-spacing:0.2px;">${b.name}</div>
            <div style="font-size:9px;font-weight:800;color:${b.accentColor};background:${b.bgBadge};border:1px solid ${b.borderColor};border-radius:4px;padding:1px 6px;margin-top:5px;letter-spacing:0.5px;text-transform:uppercase;">${b.tag}</div>
          </div>
        `,
        content: {
          type: 'text',
          content: b.content,
          droppable: false,
          draggable: true,
          style: { display: 'inline', 'font-weight': 'inherit' },
        },
        category: { id: 'personalization', label: '⚡ Smart Tags', open: true },
        attributes: { title: b.title },
      });
    });

    // Configure 'image' component with Auto Resize trait and responsive behavior
    editor.DomComponents.addType('image', {
      extend: 'image',
      model: {
        defaults: {
          resizable: {
            ratioDefault: 1,
          },
          traits: [
            'alt',
            {
              type: 'select',
              name: 'auto-resize',
              label: 'Auto Resize',
              options: [
                { id: 'responsive', name: 'Auto Resize (Responsive 100%)' },
                { id: 'fit-width', name: 'Fit Full Width (100%)' },
                { id: 'original', name: 'Original / Fixed Size' },
              ],
              default: 'responsive',
              changeProp: 1,
            },
          ],
        },
        init() {
          this.listenTo(this, 'change:auto-resize', this.handleAutoResizeChange);
          const style = this.getStyle() || {};
          if (!style['max-width'] && this.get('auto-resize') !== 'original') {
            this.handleAutoResizeChange();
          }
        },
        handleAutoResizeChange() {
          const mode = this.get('auto-resize') || 'responsive';
          if (mode === 'responsive') {
            this.addStyle({
              'max-width': '100%',
              'height': 'auto',
              'display': 'inline-block',
            });
            this.removeStyle('width');
          } else if (mode === 'fit-width') {
            this.addStyle({
              'width': '100%',
              'max-width': '100%',
              'height': 'auto',
              'display': 'block',
            });
          } else if (mode === 'original') {
            this.removeStyle('max-width');
            this.removeStyle('width');
          }
        },
      },
    });

    // Add Auto Resize button to the image toolbar
    editor.on('component:selected', (model) => {
      if (model && model.is('image')) {
        const toolbar = [...(model.get('toolbar') || [])];
        if (!toolbar.some((t) => t.command === 'image-auto-resize')) {
          toolbar.unshift({
            attributes: { class: 'fa fa-arrows-alt', title: 'Auto Resize (Responsive 100%)' },
            command: 'image-auto-resize',
          });
          model.set('toolbar', toolbar);
        }
      }
    });

    // Command to toggle Auto Resize on selected image
    editor.Commands.add('image-auto-resize', {
      run(ed) {
        const selected = ed.getSelected();
        if (selected && selected.is('image')) {
          const current = selected.getStyle() || {};
          const isResponsive = current['max-width'] === '100%';
          if (isResponsive) {
            selected.removeStyle('max-width');
            selected.removeStyle('display');
            selected.set('auto-resize', 'original');
          } else {
            selected.addStyle({
              'max-width': '100%',
              'height': 'auto',
              'display': 'inline-block',
            });
            selected.removeStyle('width');
            selected.set('auto-resize', 'responsive');
          }
        }
      },
    });

    // Helper to clean orphaned tag nodes and stray tags sitting outside text sections
    const cleanStrayTagNodes = () => {
      try {
        const canvasDoc = editor.Canvas?.getDocument();
        if (!canvasDoc) return;

        let modified = false;

        // 1. Remove orphaned raw text nodes sitting directly under td, th, tr, tbody, table
        const containers = canvasDoc.querySelectorAll('td, th, tr, tbody, table');
        containers.forEach((container) => {
          Array.from(container.childNodes).forEach((child) => {
            if (child.nodeType === Node.TEXT_NODE) {
              const txt = (child.textContent || '').trim();
              if (txt.startsWith('{{') && txt.endsWith('}}')) {
                child.remove();
                modified = true;
              }
            }
          });
        });

        // 2. Remove accidental stray paragraphs/divs whose only content is {{tag}} outside main paragraphs
        const strayBlocks = canvasDoc.querySelectorAll('td > p, td > div, td > span');
        strayBlocks.forEach((block) => {
          const txt = (block.textContent || '').trim();
          if (/^\{\{[a-zA-Z0-9_]+\}\}$/.test(txt)) {
            const parent = block.parentElement;
            if (parent && parent.querySelectorAll('p, h2, h3').length > 1) {
              block.remove();
              modified = true;
            }
          }
        });

        // 3. Fix nested/corrupted tags like {{sende{{contact_name}}r_name}}
        const allTextEls = canvasDoc.querySelectorAll('h1, h2, h3, h4, p, span, td, div');
        allTextEls.forEach((el) => {
          if (el.innerHTML && /\{\{[a-zA-Z0-9_]*\{\{([a-zA-Z0-9_]+)\}\}[a-zA-Z0-9_]*\}\}/.test(el.innerHTML)) {
            el.innerHTML = el.innerHTML.replace(/\{\{[a-zA-Z0-9_]*\{\{([a-zA-Z0-9_]+)\}\}[a-zA-Z0-9_]*\}\}/g, '{{$1}}');
            modified = true;
          }
        });

        // 4. Sync models in GrapesJS
        const wrapper = editor.getWrapper();
        if (wrapper) {
          wrapper.find('text').forEach((c) => {
            const content = c.get('content') || '';
            if (/\{\{[a-zA-Z0-9_]*\{\{([a-zA-Z0-9_]+)\}\}[a-zA-Z0-9_]*\}\}/.test(content)) {
              c.set('content', content.replace(/\{\{[a-zA-Z0-9_]*\{\{([a-zA-Z0-9_]+)\}\}[a-zA-Z0-9_]*\}\}/g, '{{$1}}'));
              modified = true;
            }
          });
        }

        if (modified) {
          editor.trigger('change:canvasOffset');
        }
      } catch (err) {
        // ignore
      }
    };

    // Attach HTML5 drag-and-drop listener to the canvas iframe document
    const attachCanvasDropListeners = () => {
      try {
        const canvasDoc = editor.Canvas.getDocument();
        if (!canvasDoc || canvasDoc._hasTagDropListeners) return;
        canvasDoc._hasTagDropListeners = true;

        canvasDoc.addEventListener('dragenter', (e) => {
          e.preventDefault();
        });

        canvasDoc.addEventListener('dragover', (e) => {
          e.preventDefault();
          try {
            e.dataTransfer.dropEffect = 'copy';
          } catch (_) {}

          // Position caret so the user sees live feedback where the tag will land
          let range = null;
          if (canvasDoc.caretRangeFromPoint) {
            range = canvasDoc.caretRangeFromPoint(e.clientX, e.clientY);
          } else if (canvasDoc.caretPositionFromPoint) {
            const pos = canvasDoc.caretPositionFromPoint(e.clientX, e.clientY);
            if (pos) {
              range = canvasDoc.createRange();
              range.setStart(pos.offsetNode, pos.offset);
              range.collapse(true);
            }
          }
          if (range) {
            const sel = canvasDoc.getSelection();
            if (sel) {
              sel.removeAllRanges();
              sel.addRange(range);
            }
          }
        });

        canvasDoc.addEventListener('drop', (e) => {
          const token = e.dataTransfer.getData('text/plain') || e.dataTransfer.getData('text') || e.dataTransfer.getData('text/html');
          if (!token || (!token.startsWith('{{') && !token.includes('{{'))) return;

          e.preventDefault();
          e.stopPropagation();

          // 1. Find the target element under cursor
          let targetEl = canvasDoc.elementFromPoint(e.clientX, e.clientY);
          if (!targetEl) targetEl = canvasDoc.body;

          // Find closest text element (p, h1, h2, h3, h4, h5, h6, span, li, a)
          let textEl = targetEl.closest('p, h1, h2, h3, h4, h5, h6, span, li, a');

          // If dropped outside of any text element (e.g. on td background or cell margin):
          if (!textEl) {
            const allTextEls = Array.from(canvasDoc.querySelectorAll('h1, h2, h3, h4, p, span'));
            if (allTextEls.length > 0) {
              let closest = allTextEls[0];
              let minDistance = Infinity;
              allTextEls.forEach((el) => {
                const rect = el.getBoundingClientRect();
                const midY = rect.top + rect.height / 2;
                const dist = Math.abs(e.clientY - midY);
                if (dist < minDistance) {
                  minDistance = dist;
                  closest = el;
                }
              });
              textEl = closest;
            }
          }

          if (textEl) {
            let range = null;
            if (canvasDoc.caretRangeFromPoint) {
              range = canvasDoc.caretRangeFromPoint(e.clientX, e.clientY);
            } else if (canvasDoc.caretPositionFromPoint) {
              const pos = canvasDoc.caretPositionFromPoint(e.clientX, e.clientY);
              if (pos) {
                range = canvasDoc.createRange();
                range.setStart(pos.offsetNode, pos.offset);
                range.collapse(true);
              }
            }

            let inserted = false;

            // If range is within the text element, check for placeholder replacement or insertion
            if (range && textEl.contains(range.startContainer)) {
              const node = range.startContainer;
              if (node.nodeType === Node.TEXT_NODE) {
                const text = node.textContent || '';
                const offset = range.startOffset;

                // Check if dropped on/inside an existing tag like {{sender_name}}
                const tagRegex = /\{\{[a-zA-Z0-9_\s]+\}\}/g;
                let match;
                let replaceRange = null;
                while ((match = tagRegex.exec(text)) !== null) {
                  const startIdx = match.index;
                  const endIdx = match.index + match[0].length;
                  if (offset >= startIdx && offset <= endIdx) {
                    replaceRange = { start: startIdx, end: endIdx };
                    break;
                  }
                }

                if (replaceRange) {
                  // Replace existing tag cleanly
                  const before = text.slice(0, replaceRange.start);
                  const after = text.slice(replaceRange.end);
                  node.textContent = before + token + after;
                  inserted = true;
                } else {
                  // Insert with proper word boundary spacing
                  const charBefore = offset > 0 ? text[offset - 1] : '';
                  const charAfter = offset < text.length ? text[offset] : '';
                  const needsSpaceBefore = charBefore && !/\s/.test(charBefore) && charBefore !== '{';
                  const needsSpaceAfter = charAfter && !/\s/.test(charAfter) && charAfter !== '}';
                  const insertText = (needsSpaceBefore ? ' ' : '') + token + (needsSpaceAfter ? ' ' : '');

                  const before = text.slice(0, offset);
                  const after = text.slice(offset);
                  node.textContent = before + insertText + after;
                  inserted = true;
                }
              }
            }

            if (!inserted) {
              const cur = textEl.innerHTML || '';
              textEl.innerHTML = cur.trim() + ' ' + token;
            }

            // Clean any nested corrupted tags
            if (textEl.innerHTML && /\{\{[a-zA-Z0-9_]*\{\{([a-zA-Z0-9_]+)\}\}[a-zA-Z0-9_]*\}\}/.test(textEl.innerHTML)) {
              textEl.innerHTML = textEl.innerHTML.replace(/\{\{[a-zA-Z0-9_]*\{\{([a-zA-Z0-9_]+)\}\}[a-zA-Z0-9_]*\}\}/g, '{{$1}}');
            }

            // Sync GrapesJS model
            let compEl = textEl;
            while (compEl && compEl !== canvasDoc.body && !compEl.__gjs_view) {
              compEl = compEl.parentElement;
            }
            if (compEl && compEl.__gjs_view && compEl.__gjs_view.model) {
              const model = compEl.__gjs_view.model;
              if (model.is('text')) {
                model.set('content', compEl.innerHTML);
              }
              model.trigger('change:content');

              // Select and enable text editing
              try {
                editor.select(model);
                setTimeout(() => {
                  try {
                    const view = model.getView();
                    if (view && typeof view.enableEditing === 'function' && !view.rteEnabled) {
                      view.enableEditing();
                    }
                  } catch (_) {}
                }, 50);
              } catch (_) {}
            }
          }

          // Automatically clean any stray nodes
          cleanStrayTagNodes();

          editor.trigger('change:canvasOffset');
          dirtyRef.current = true;
          onDirty && onDirty();
        });

        // Single-click on text elements to immediately enter editing mode
        canvasDoc.addEventListener('click', (e) => {
          const textEl = e.target.closest('p, h1, h2, h3, h4, span');
          if (textEl) {
            let compEl = textEl;
            while (compEl && compEl !== canvasDoc.body && !compEl.__gjs_view) {
              compEl = compEl.parentElement;
            }
            if (compEl && compEl.__gjs_view && compEl.__gjs_view.model) {
              const model = compEl.__gjs_view.model;
              if (model.is('text')) {
                setTimeout(() => {
                  try {
                    const view = model.getView();
                    if (view && typeof view.enableEditing === 'function' && !view.rteEnabled) {
                      view.enableEditing();
                    }
                  } catch (_) {
                    try { editor.runCommand('core:component-enter'); } catch (__) {}
                  }
                }, 30);
              }
            }
          }
        });
      } catch (err) {
        // ignore
      }
    };

    // Inject canvas responsive styles for desktop, tablet, and mobile views
    editor.on('load', () => {
      try {
        const canvasDoc = editor.Canvas.getDocument();
        if (canvasDoc && canvasDoc.head) {
          const styleEl = canvasDoc.createElement('style');
          styleEl.setAttribute('id', 'gjs-responsive-images');
          styleEl.innerHTML = `
            img {
              max-width: 100% !important;
              height: auto !important;
              box-sizing: border-box;
            }
            body {
              background-color: #f8fafc;
              margin: 0;
              padding: 24px 12px;
              box-sizing: border-box;
            }
          `;
          canvasDoc.head.appendChild(styleEl);
        }
        attachCanvasDropListeners();
        setTimeout(cleanStrayTagNodes, 300);
      } catch (err) {
        // ignore
      }
    });

    // Also attach drop listeners if canvas is ready
    setTimeout(() => {
      attachCanvasDropListeners();
      cleanStrayTagNodes();
    }, 400);

    // Also attach dragover/drop to outer container
    const containerEl = containerRef.current;
    if (containerEl) {
      const handleContainerDragOver = (e) => {
        e.preventDefault();
        try { e.dataTransfer.dropEffect = 'copy'; } catch (_) {}
      };
      const handleContainerDrop = (e) => {
        const token = e.dataTransfer.getData('text/plain') || e.dataTransfer.getData('text') || e.dataTransfer.getData('text/html');
        if (token && (token.startsWith('{{') || token.includes('{{'))) {
          e.preventDefault();
          insertTagInternal(token);
        }
      };
      containerEl.addEventListener('dragover', handleContainerDragOver);
      containerEl.addEventListener('drop', handleContainerDrop);
    }

    // Automatically apply responsive styling to any newly added image
    editor.on('component:add', (component) => {
      if (component.is('image')) {
        const style = component.getStyle() || {};
        if (!style['max-width'] && component.get('auto-resize') !== 'original') {
          component.addStyle({
            'max-width': '100%',
            'height': 'auto',
            'display': 'inline-block',
          });
          component.set('auto-resize', 'responsive');
        }
      }
    });

    // Automatically activate editing when text component is selected
    editor.on('component:selected', (model) => {
      if (model && model.is('text')) {
        setTimeout(() => {
          try {
            const view = model.getView();
            if (view && typeof view.enableEditing === 'function' && !view.rteEnabled) {
              view.enableEditing();
            }
          } catch (e) {
            try { editor.runCommand('core:component-enter'); } catch (_) {}
          }
        }, 40);
      }
    });

    // Helper to clean orphaned signature title text sitting loose in wrapper root
    const cleanOrphanedBodyText = () => {
      try {
        const wrapper = editor.getWrapper();
        if (!wrapper) return;
        wrapper.components().forEach((c) => {
          if (c && c.is('text')) {
            const text = (c.get('content') || '').trim();
            if (text === 'Plus UAE Email Signature' || text === 'PlusUAE Fahad Signature') {
              c.remove();
            }
          }
        });
      } catch (e) {
        // ignore
      }
    };

    // Helper to apply responsive styling to all existing images in loaded project
    const applyResponsiveToExistingImages = () => {
      try {
        const wrapper = editor.getWrapper();
        if (wrapper) {
          wrapper.find('img').forEach((img) => {
            const style = img.getStyle() || {};
            if (!style['max-width'] && img.get('auto-resize') !== 'original') {
              img.addStyle({
                'max-width': '100%',
                'height': 'auto',
                'display': 'inline-block',
              });
              img.set('auto-resize', 'responsive');
            }
          });
        }
        cleanOrphanedBodyText();
        cleanStrayTagNodes();
      } catch (e) {
        // ignore
      }
    };

    const hasProject = projectData && Array.isArray(projectData.pages) && projectData.pages.length > 0;
    if (hasProject) {
      editor.loadProjectData(projectData);
      applyResponsiveToExistingImages();
    } else if (initialHtml) {
      editor.setComponents(initialHtml);
      applyResponsiveToExistingImages();
    }

    // Internal helper for inserting tags into active text or primary paragraph
    const insertTagInternal = (token) => {
      if (!editor) return;
      try {
        const doc = editor.Canvas?.getDocument();
        const sel = doc?.getSelection();

        // 1. If actively typing in a text component, insert directly at cursor
        if (sel && sel.rangeCount > 0 && doc.activeElement && doc.activeElement !== doc.body) {
          const range = sel.getRangeAt(0);
          range.deleteContents();
          const node = doc.createTextNode(' ' + token + ' ');
          range.insertNode(node);
          range.setStartAfter(node);
          range.collapse(true);

          let el = range.startContainer;
          while (el && el !== doc.body && !el.__gjs_view) {
            el = el.parentElement;
          }
          if (el && el.__gjs_view && el.__gjs_view.model) {
            const comp = el.__gjs_view.model;
            if (comp.is('text')) {
              comp.set('content', el.innerHTML);
            }
            comp.trigger('change:content');
          }
        } else {
          // 2. If a text component is selected, append with clean space
          const selected = editor.getSelected();
          if (selected && selected.is('text')) {
            const cur = selected.get('content') || '';
            selected.set('content', cur.trim() + ' ' + token);
          } else {
            // 3. Find primary text paragraph in the card
            const wrapper = editor.getWrapper();
            const mainP = wrapper?.find('p')[0] || wrapper?.find('h2')[0];
            if (mainP) {
              const cur = mainP.get('content') || '';
              mainP.set('content', cur.trim() + ' ' + token);
              editor.select(mainP);
            }
          }
        }
      } catch (err) {
        // ignore
      }
      cleanStrayTagNodes();
      dirtyRef.current = true;
      onDirty && onDirty();
    };

    // Ignore the burst of change events caused by initial loading.
    const armTimer = setTimeout(() => {
      changeCount.current = 0;
      dirtyRef.current = false;
      editor.on('update', () => {
        changeCount.current += 1;
        if (!dirtyRef.current) {
          dirtyRef.current = true;
          onDirty && onDirty();
        }
      });
    }, 600);

    return () => {
      clearTimeout(armTimer);
      document.getElementById('gjs-smart-tags-block-style')?.remove();
      editor.destroy();
      editorRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useImperativeHandle(ref, () => ({
    getData() {
      const editor = editorRef.current;
      if (!editor) return null;
      let html = '';
      try {
        html = editor.runCommand('gjs-get-inlined-html') || '';
      } catch (e) {
        html = editor.getHtml();
      }
      html = ensureResponsiveImages(html);
      return { projectData: editor.getProjectData(), html };
    },
    loadHtml(html) {
      const editor = editorRef.current;
      if (!editor) return;
      editor.setComponents(html);
      dirtyRef.current = true;
      onDirty && onDirty();
    },
    appendHtml(html) {
      const editor = editorRef.current;
      if (!editor) return;

      // Clean html: strip <head>, <title>, and any loose leading text before any HTML tag
      let safeHtml = (html || '')
        .replace(/<head\b[^>]*>[\s\S]*?<\/head>/gi, '')
        .replace(/<title\b[^>]*>[\s\S]*?<\/title>/gi, '')
        .trim();

      // Strip loose leading text before any HTML tag (e.g. leaked signature title text)
      safeHtml = safeHtml.replace(/^[^<]+(?=<table|<div|<p|<tr|<td)/i, '').trim() || safeHtml;

      const wrapper = editor.getWrapper();
      const selected = editor.getSelected();

      if (selected) {
        if (selected.is('cell') || selected.is('td')) {
          selected.append(safeHtml);
        } else {
          const parent = selected.parent();
          if (parent) {
            parent.append(safeHtml);
          } else {
            selected.append(safeHtml);
          }
        }
      } else {
        const hasCenteredConstraint = safeHtml.includes('max-width') && (safeHtml.includes('margin: 0 auto') || safeHtml.includes('margin:0 auto'));

        if (hasCenteredConstraint) {
          editor.addComponents(safeHtml);
        } else {
          const mainTd = wrapper?.find('td')[0];
          if (mainTd) {
            mainTd.append(`<div style="margin-top:20px;padding-top:14px;border-top:1px solid #e2e8f0;">${safeHtml}</div>`);
          } else {
            editor.addComponents(`<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:16px auto 0 auto;"><tr><td>${safeHtml}</td></tr></table>`);
          }
        }
      }

      dirtyRef.current = true;
      onDirty && onDirty();
    },
    insertTag(token) {
      const editor = editorRef.current;
      if (!editor) return;

      try {
        const doc = editor.Canvas?.getDocument();
        const sel = doc?.getSelection();
        if (sel && sel.rangeCount > 0 && doc.activeElement && doc.activeElement !== doc.body) {
          const range = sel.getRangeAt(0);
          range.deleteContents();
          const node = doc.createTextNode(' ' + token + ' ');
          range.insertNode(node);
          range.setStartAfter(node);
          range.collapse(true);

          let el = range.startContainer;
          while (el && el !== doc.body && !el.__gjs_view) {
            el = el.parentElement;
          }
          if (el && el.__gjs_view && el.__gjs_view.model) {
            const comp = el.__gjs_view.model;
            if (comp.is('text')) {
              comp.set('content', el.innerHTML);
            }
            comp.trigger('change:content');
          }
        } else {
          const selected = editor.getSelected();
          if (selected && selected.is('text')) {
            const cur = selected.get('content') || '';
            selected.set('content', cur.trim() + ' ' + token);
          } else {
            const wrapper = editor.getWrapper();
            const mainP = wrapper?.find('p')[0] || wrapper?.find('h2')[0];
            if (mainP) {
              const cur = mainP.get('content') || '';
              mainP.set('content', cur.trim() + ' ' + token);
              editor.select(mainP);
            }
          }
        }
      } catch (err) {
        // ignore
      }

      cleanStrayTagNodes();
      dirtyRef.current = true;
      onDirty && onDirty();
    },
    cleanStrayTags() {
      cleanStrayTagNodes();
      dirtyRef.current = true;
      onDirty && onDirty();
    },
    isDirty: () => dirtyRef.current,
    markClean() {
      dirtyRef.current = false;
    },
  }));

  return <div ref={containerRef} className="border border-slate-200 rounded-xl overflow-hidden bg-white" />;
});

export default GrapesEditor;
