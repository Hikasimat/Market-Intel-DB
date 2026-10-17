import React, { useState, useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import {
  Undo2, Redo2, Type, Image as ImageIcon, MousePointerClick, Minus,
  Space, Columns2, PenTool, Eye, Save, Code2, Plus, Trash2, Copy,
  ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Sparkles, GripVertical, Check, X, Smartphone, Monitor, Rows2,
  FileCode, Upload
} from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi } from '../../../services/designApi';
import {
  generateEmailHtml,
  parseHtmlToBlocks,
  ensureResponsiveImages,
  fillSample,
  resolveImageUrl,
  SMART_TAGS,
} from './emailHtmlGenerator';
import ColumnLayoutPicker, { createColumnBlock, changeBlockColumnLayout, COLUMN_LAYOUTS } from './ColumnLayoutPicker';
import PropertiesPanel from './PropertiesPanel';
import RichTextToolbar from './RichTextToolbar';
import SignatureBuilderModal from '../SignatureBuilderModal';

const MAX_HISTORY = 30;

const STARTER_BLOCKS = [
  {
    id: 'block_header_default',
    type: 'header',
    title: 'Market Intelligence Briefing',
    subtitle: 'Exclusive Solutions for {{company_name}}',
    logoUrl: '',
    logoWidth: 120,
    backgroundColor: '#0f172a',
    textColor: '#ffffff',
    align: 'center',
    padding: '28px 24px',
  },
  {
    id: 'block_text_greeting',
    type: 'text',
    content: `
      <h2 style="margin: 0 0 16px 0; color: #0f172a; font-size: 20px; font-weight: 700;">
        Hello {{contact_name}},
      </h2>
      <p style="margin: 0 0 14px 0; color: #334155; font-size: 15px; line-height: 1.6;">
        I'm reaching out from {{sender_name}} to introduce our comprehensive market intelligence and corporate advisory services tailored for {{company_name}}.
      </p>
      <p style="margin: 0 0 14px 0; color: #334155; font-size: 15px; line-height: 1.6;">
        We have identified strategic growth opportunities in your industry and would welcome a brief 10-minute introductory call.
      </p>
    `.trim(),
    align: 'left',
    fontSize: 15,
    color: '#334155',
    lineHeight: '1.6',
    padding: '24px 28px',
    backgroundColor: 'transparent',
  },
  {
    id: 'block_button_cta',
    type: 'button',
    label: 'Schedule a 10-Minute Call',
    url: '#',
    backgroundColor: '#2563eb',
    textColor: '#ffffff',
    fontSize: 15,
    borderRadius: 8,
    align: 'center',
    padding: '16px 24px',
  },
  {
    id: 'block_divider_1',
    type: 'divider',
    color: '#e2e8f0',
    thickness: 1,
    width: 100,
    paddingTop: 16,
    paddingBottom: 16,
  },
  {
    id: 'block_text_closing',
    type: 'text',
    content: `
      <p style="margin: 0; color: #334155; font-size: 15px; line-height: 1.6;">
        Looking forward to connecting with you.
      </p>
    `.trim(),
    align: 'left',
    fontSize: 15,
    color: '#334155',
    lineHeight: '1.6',
    padding: '8px 28px 20px 28px',
    backgroundColor: 'transparent',
  },
  {
    id: 'block_footer_default',
    type: 'footer',
    text: 'Market Intel DB • Corporate Intelligence & Outreach Management',
    unsubscribeText: 'If you prefer not to receive updates from our team,',
    unsubscribeUrl: '{{unsubscribe_url}}',
    backgroundColor: '#f8fafc',
    textColor: '#64748b',
    align: 'center',
    padding: '20px',
  },
];

const SimpleEmailEditor = forwardRef(function SimpleEmailEditor(
  { projectData, initialHtml, onDirty, height = '720px', emptyCanvas = false, kind },
  ref
) {
  // Initialize blocks from projectData or initialHtml
  const [blocks, setBlocks] = useState(() => {
    if (projectData && Array.isArray(projectData.blocks) && projectData.blocks.length > 0) {
      return projectData.blocks;
    }
    if (initialHtml && initialHtml.trim()) {
      return parseHtmlToBlocks(initialHtml);
    }
    if (emptyCanvas) {
      return [];
    }
    return STARTER_BLOCKS;
  });

  const [globalStyles, setGlobalStyles] = useState(() => {
    return projectData?.globalStyles || {
      backgroundColor: '#f1f5f9',
      canvasColor: '#ffffff',
      maxWidth: '600px',
    };
  });

  // History for Undo/Redo
  const [history, setHistory] = useState([blocks]);
  const [historyIdx, setHistoryIdx] = useState(0);

  // Selection
  const [selectedBlockId, setSelectedBlockId] = useState(null);
  const [selectedColumnId, setSelectedColumnId] = useState(null);
  const [selectedSubElementId, setSelectedSubElementId] = useState(null);

  // Modals & Panels
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const [showSigBuilderModal, setShowSigBuilderModal] = useState(false);
  const [showInsertSigMenu, setShowInsertSigMenu] = useState(false);
  const [savedSignatures, setSavedSignatures] = useState([]);
  const [previewModal, setPreviewModal] = useState(null); // { mobile: boolean, source: boolean, tab?: 'view' | 'import' }
  const [importHtmlInput, setImportHtmlInput] = useState('');
  const [copiedSource, setCopiedSource] = useState(false);

  // Drag state
  const [draggedBlockIndex, setDraggedBlockIndex] = useState(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);
  const [draggedSubElement, setDraggedSubElement] = useState(null);
  const [subDropTarget, setSubDropTarget] = useState(null);

  // Active text editing ref for RichTextToolbar
  const activeTextElRef = useRef(null);
  const savedRangeRef = useRef(null);
  const lastFocusedElRef = useRef(null);
  const dirtyRef = useRef(false);

  // Load saved signatures for easy insertion
  useEffect(() => {
    designApi.list('signature')
      .then((data) => setSavedSignatures(data || []))
      .catch(() => {});
  }, []);

  const markDirty = () => {
    if (!dirtyRef.current) {
      dirtyRef.current = true;
      onDirty && onDirty();
    }
  };

  const pushHistory = (newBlocks) => {
    const updatedHistory = history.slice(0, historyIdx + 1);
    updatedHistory.push(newBlocks);
    if (updatedHistory.length > MAX_HISTORY) updatedHistory.shift();
    setHistory(updatedHistory);
    setHistoryIdx(updatedHistory.length - 1);
    setBlocks(newBlocks);
    markDirty();
  };

  const handleUndo = () => {
    if (historyIdx > 0) {
      const newIdx = historyIdx - 1;
      setHistoryIdx(newIdx);
      setBlocks(history[newIdx]);
      markDirty();
    }
  };

  const handleRedo = () => {
    if (historyIdx < history.length - 1) {
      const newIdx = historyIdx + 1;
      setHistoryIdx(newIdx);
      setBlocks(history[newIdx]);
      markDirty();
    }
  };

  // Block management
  const addBlock = (newBlock, atIndex = null) => {
    const updated = [...blocks];
    if (atIndex !== null && atIndex >= 0) {
      updated.splice(atIndex, 0, newBlock);
    } else {
      updated.push(newBlock);
    }
    pushHistory(updated);
    setSelectedBlockId(newBlock.id);
    setSelectedColumnId(null);
    setSelectedSubElementId(null);
  };

  const updateBlock = (blockId, updates) => {
    const updated = blocks.map((b) => (b.id === blockId ? { ...b, ...updates } : b));
    pushHistory(updated);
  };

  const updateSubElement = (blockId, columnId, subId, updates) => {
    const updated = blocks.map((b) => {
      if (b.id !== blockId) return b;
      const cols = (b.columns || []).map((c) => {
        if (c.id !== columnId) return c;
        const els = (c.elements || []).map((el) => {
          if (el.id === subId) {
            return { ...el, ...updates };
          }
          if (el.type === 'row') {
            const updatedRCols = (el.columns || []).map((rc) => ({
              ...rc,
              elements: (rc.elements || []).map((rel) =>
                rel.id === subId ? { ...rel, ...updates } : rel
              ),
            }));
            return { ...el, columns: updatedRCols };
          }
          return el;
        });
        return { ...c, elements: els };
      });
      return { ...b, columns: cols };
    });
    pushHistory(updated);
  };

  const updateColumn = (blockId, columnId, updates) => {
    const updated = blocks.map((b) => {
      if (b.id !== blockId) return b;
      const cols = (b.columns || []).map((c) => {
        if (c.id !== columnId) return c;
        return { ...c, ...updates };
      });
      return { ...b, columns: cols };
    });
    pushHistory(updated);
  };

  const cleanupRowsInColumn = (col) => {
    if (!col || !col.elements) return;
    const newEls = [];
    for (const el of col.elements) {
      if (el.type === 'row') {
        const allRowEls = (el.columns || []).flatMap((rc) => rc.elements || []);
        if (allRowEls.length === 0) {
          continue;
        } else if (allRowEls.length === 1) {
          newEls.push(allRowEls[0]);
        } else {
          newEls.push(el);
        }
      } else {
        newEls.push(el);
      }
    }
    col.elements = newEls;
  };

  const deleteBlock = (blockId, columnId = null, subId = null) => {
    if (columnId && subId) {
      // Delete inside column (including nested row elements)
      const updated = blocks.map((b) => {
        if (b.id !== blockId) return b;
        const cols = (b.columns || []).map((c) => {
          if (c.id !== columnId) return c;
          const filtered = (c.elements || []).filter((el) => el.id !== subId).map((el) => {
            if (el.type === 'row') {
              return {
                ...el,
                columns: (el.columns || []).map((rc) => ({
                  ...rc,
                  elements: (rc.elements || []).filter((rel) => rel.id !== subId),
                })),
              };
            }
            return el;
          });
          const newCol = { ...c, elements: filtered };
          cleanupRowsInColumn(newCol);
          return newCol;
        });
        return { ...b, columns: cols };
      });
      pushHistory(updated);
      setSelectedSubElementId(null);
    } else {
      // Delete top-level block
      const updated = blocks.filter((b) => b.id !== blockId);
      pushHistory(updated);
      if (selectedBlockId === blockId) {
        setSelectedBlockId(null);
        setSelectedColumnId(null);
        setSelectedSubElementId(null);
      }
    }
    toast.info('Element removed');
  };

  const duplicateBlock = (blockId) => {
    const idx = blocks.findIndex((b) => b.id === blockId);
    if (idx === -1) return;
    const cloned = JSON.parse(JSON.stringify(blocks[idx]));
    cloned.id = `block_${Date.now()}_copy`;
    const updated = [...blocks];
    updated.splice(idx + 1, 0, cloned);
    pushHistory(updated);
    setSelectedBlockId(cloned.id);
  };

  const moveBlock = (index, dir) => {
    const targetIdx = index + dir;
    if (targetIdx < 0 || targetIdx >= blocks.length) return;
    const updated = [...blocks];
    const [moved] = updated.splice(index, 1);
    updated.splice(targetIdx, 0, moved);
    pushHistory(updated);
  };

  // Add Element to a Column
  const addElementToColumn = (blockId, columnId, type) => {
    let newEl = null;
    const id = `sub_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    if (type === 'text') {
      newEl = { id, type: 'text', content: '<p>Click to edit column text...</p>', align: 'left', fontSize: 14, color: '#334155', backgroundColor: 'transparent' };
    } else if (type === 'image') {
      newEl = { id, type: 'image', url: 'https://placehold.co/300x180/e2e8f0/475569?text=Image', width: 260, align: 'center', backgroundColor: 'transparent' };
    } else if (type === 'button') {
      newEl = { id, type: 'button', label: 'Learn More', url: '#', backgroundColor: '#2563eb', textColor: '#fff', align: 'center' };
    } else if (type === 'row') {
      newEl = {
        id,
        type: 'row',
        layout: '2-col-equal',
        backgroundColor: 'transparent',
        padding: '6px 2px',
        border: { enabled: false, color: '#e2e8f0', width: 1 },
        columns: [
          {
            id: `rcol_${Date.now()}_1`,
            widthPercent: 50,
            backgroundColor: 'transparent',
            padding: '6px',
            elements: [
              { id: `rsub_${Date.now()}_1`, type: 'text', content: '<p>Row item 1...</p>', align: 'left', fontSize: 13, color: '#334155', backgroundColor: 'transparent' },
            ],
          },
          {
            id: `rcol_${Date.now()}_2`,
            widthPercent: 50,
            backgroundColor: 'transparent',
            padding: '6px',
            elements: [
              { id: `rsub_${Date.now()}_2`, type: 'text', content: '<p>Row item 2...</p>', align: 'left', fontSize: 13, color: '#334155', backgroundColor: 'transparent' },
            ],
          },
        ],
      };
    } else if (type === 'divider') {
      newEl = { id, type: 'divider', color: '#e2e8f0', thickness: 1, width: 100 };
    } else if (type === 'spacer') {
      newEl = { id, type: 'spacer', height: 16 };
    }

    if (!newEl) return;

    const updated = blocks.map((b) => {
      if (b.id !== blockId) return b;
      const cols = (b.columns || []).map((c) => {
        if (c.id !== columnId) return c;
        return { ...c, elements: [...(c.elements || []), newEl] };
      });
      return { ...b, columns: cols };
    });

    pushHistory(updated);
    setSelectedBlockId(blockId);
    setSelectedColumnId(columnId);
    setSelectedSubElementId(newEl.id);
  };

  // Sub-element drag handlers
  const handleSubDragStart = (e, blockId, colId, subEl) => {
    e.stopPropagation();
    setDraggedSubElement({ blockId, colId, elementId: subEl.id, element: subEl });
    e.dataTransfer.setData('text/email-subelement', JSON.stringify({ blockId, colId, elementId: subEl.id }));
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleSubDragOver = (e, targetBlockId, targetColId, targetSubEl) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    if (!draggedSubElement) return;
    if (draggedSubElement.elementId === targetSubEl.id) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const relX = e.clientX - rect.left;
    const relY = e.clientY - rect.top;
    const wRatio = relX / rect.width;
    const hRatio = relY / rect.height;

    // Detect left, right, top, bottom
    let pos = 'bottom';
    if (wRatio < 0.28) {
      pos = 'left';
    } else if (wRatio > 0.72) {
      pos = 'right';
    } else if (hRatio < 0.5) {
      pos = 'top';
    } else {
      pos = 'bottom';
    }

    setSubDropTarget({
      blockId: targetBlockId,
      colId: targetColId,
      targetElementId: targetSubEl.id,
      position: pos,
    });
  };

  const moveSubElementInColumn = (blockId, colId, subElId, dir) => {
    const updatedBlocks = JSON.parse(JSON.stringify(blocks));
    const block = updatedBlocks.find((b) => b.id === blockId);
    if (!block) return;
    const col = (block.columns || []).find((c) => c.id === colId);
    if (!col || !col.elements) return;

    const idx = col.elements.findIndex((e) => e.id === subElId);
    if (idx !== -1) {
      const targetIdx = idx + dir;
      if (targetIdx >= 0 && targetIdx < col.elements.length) {
        const [moved] = col.elements.splice(idx, 1);
        col.elements.splice(targetIdx, 0, moved);
        pushHistory(updatedBlocks);
        setSelectedBlockId(blockId);
        setSelectedColumnId(colId);
        setSelectedSubElementId(moved.id);
        toast.success('Reordered element');
      }
      return;
    }

    // Check inside rows
    for (const el of col.elements) {
      if (el.type === 'row') {
        for (const rc of (el.columns || [])) {
          const rIdx = (rc.elements || []).findIndex((e) => e.id === subElId);
          if (rIdx !== -1) {
            const targetIdx = rIdx + dir;
            if (targetIdx >= 0 && targetIdx < rc.elements.length) {
              const [moved] = rc.elements.splice(rIdx, 1);
              rc.elements.splice(targetIdx, 0, moved);
              pushHistory(updatedBlocks);
              setSelectedBlockId(blockId);
              setSelectedColumnId(colId);
              setSelectedSubElementId(moved.id);
              toast.success('Reordered element');
            }
            return;
          }
        }
      }
    }
  };

  const handleSubDrop = (e, targetBlockId, targetColId, targetSubEl) => {
    e.preventDefault();
    e.stopPropagation();

    // Check if it's a smart tag first
    const smartTag = e.dataTransfer.getData('smart-tag') || e.dataTransfer.getData('text/plain');
    if (smartTag && smartTag.startsWith('{{')) {
      if (targetSubEl.type === 'text') {
        insertTokenIntoTarget(smartTag, targetBlockId, targetColId, targetSubEl.id);
      }
      setDraggedSubElement(null);
      setSubDropTarget(null);
      return;
    }

    const subData = e.dataTransfer.getData('text/email-subelement');
    let info = draggedSubElement;
    if (!info && subData) {
      try {
        info = JSON.parse(subData);
      } catch (err) {}
    }
    if (!info) return;

    const pos = subDropTarget?.position || 'bottom';
    moveSubElementBetweenColumns(
      info.blockId,
      info.colId,
      info.elementId,
      targetBlockId,
      targetColId,
      targetSubEl.id,
      pos
    );

    setDraggedSubElement(null);
    setSubDropTarget(null);
  };

  const moveSubElementToColumn = (blockId, fromColId, elementId, toColIdx) => {
    const updatedBlocks = JSON.parse(JSON.stringify(blocks));
    const block = updatedBlocks.find((b) => b.id === blockId);
    if (!block || !block.columns || toColIdx < 0 || toColIdx >= block.columns.length) return;

    const fromCol = block.columns.find((c) => c.id === fromColId);
    if (!fromCol) return;

    const elIdx = (fromCol.elements || []).findIndex((e) => e.id === elementId);
    if (elIdx === -1) return;

    const [movedEl] = fromCol.elements.splice(elIdx, 1);
    const toCol = block.columns[toColIdx];
    toCol.elements = toCol.elements || [];
    toCol.elements.push(movedEl);

    cleanupRowsInColumn(fromCol);
    cleanupRowsInColumn(toCol);

    pushHistory(updatedBlocks);
    setSelectedBlockId(blockId);
    setSelectedColumnId(toCol.id);
    setSelectedSubElementId(movedEl.id);
    toast.success('Moved element to column');
  };

  const moveSubElementBetweenColumns = (
    sourceBlockId,
    sourceColId,
    sourceElementId,
    targetBlockId,
    targetColId,
    targetElementId = null,
    position = 'column'
  ) => {
    const updatedBlocks = JSON.parse(JSON.stringify(blocks));

    // Find and extract source element from anywhere (column or nested row)
    let extractedEl = null;
    let sColRef = null;

    for (const b of updatedBlocks) {
      for (const c of (b.columns || [])) {
        const idx = (c.elements || []).findIndex((el) => el.id === sourceElementId);
        if (idx !== -1) {
          extractedEl = c.elements.splice(idx, 1)[0];
          sColRef = c;
          break;
        }
        for (const el of (c.elements || [])) {
          if (el.type === 'row') {
            for (const rc of (el.columns || [])) {
              const rIdx = (rc.elements || []).findIndex((rel) => rel.id === sourceElementId);
              if (rIdx !== -1) {
                extractedEl = rc.elements.splice(rIdx, 1)[0];
                sColRef = c;
                break;
              }
            }
            if (extractedEl) break;
          }
        }
        if (extractedEl) break;
      }
      if (extractedEl) break;
    }

    if (!extractedEl) return;

    const tBlock = updatedBlocks.find((b) => b.id === targetBlockId);
    if (!tBlock) return;
    const tCol = (tBlock.columns || []).find((c) => c.id === targetColId);
    if (!tCol) return;
    tCol.elements = tCol.elements || [];

    // Case 1: Dropped onto column directly
    if (position === 'column' || !targetElementId) {
      tCol.elements.push(extractedEl);
      if (sColRef) cleanupRowsInColumn(sColRef);
      cleanupRowsInColumn(tCol);

      pushHistory(updatedBlocks);
      setSelectedBlockId(targetBlockId);
      setSelectedColumnId(targetColId);
      setSelectedSubElementId(extractedEl.id);
      toast.success('Moved element to column');
      return;
    }

    // Case 2: Dropped relative to targetElementId
    const directIdx = tCol.elements.findIndex((el) => el.id === targetElementId);

    if (directIdx !== -1) {
      const targetEl = tCol.elements[directIdx];

      if (position === 'top') {
        tCol.elements.splice(directIdx, 0, extractedEl);
        toast.success('Moved element above');
      } else if (position === 'bottom') {
        tCol.elements.splice(directIdx + 1, 0, extractedEl);
        toast.success('Moved element below');
      } else if (position === 'left' || position === 'right') {
        // Arrange side-by-side in same column - DO NOT create parent columns!
        if (targetEl.type === 'row') {
          // targetEl is already a row, add a column to it
          const newRCol = {
            id: `rcol_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
            widthPercent: 50,
            backgroundColor: 'transparent',
            padding: '4px',
            elements: [extractedEl],
          };
          if (position === 'left') {
            targetEl.columns.unshift(newRCol);
          } else {
            targetEl.columns.push(newRCol);
          }
          const colCount = targetEl.columns.length;
          const eachW = Math.floor(100 / colCount);
          targetEl.columns.forEach((rc, i) => {
            rc.widthPercent = i === colCount - 1 ? (100 - eachW * (colCount - 1)) : eachW;
          });
          toast.success('Arranged elements side by side in row');
        } else {
          // Both are elements: arrange them side by side inside existing column
          const leftItem = position === 'left' ? extractedEl : targetEl;
          const rightItem = position === 'left' ? targetEl : extractedEl;

          const sideBySideRow = {
            id: `row_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
            type: 'row',
            layout: '2-col-equal',
            backgroundColor: 'transparent',
            padding: '2px 0px',
            border: { enabled: false, color: '#e2e8f0', width: 1 },
            columns: [
              {
                id: `rcol_${Date.now()}_1`,
                widthPercent: 50,
                backgroundColor: 'transparent',
                padding: '4px',
                elements: [leftItem],
              },
              {
                id: `rcol_${Date.now()}_2`,
                widthPercent: 50,
                backgroundColor: 'transparent',
                padding: '4px',
                elements: [rightItem],
              },
            ],
          };

          tCol.elements.splice(directIdx, 1, sideBySideRow);
          toast.success('Arranged elements side by side in row');
        }
      }
    } else {
      // Check if targetElementId is inside a row inside tCol.elements
      let foundInRow = false;
      for (const el of tCol.elements) {
        if (el.type === 'row') {
          for (let rcIdx = 0; rcIdx < (el.columns || []).length; rcIdx++) {
            const rc = el.columns[rcIdx];
            const rSubIdx = (rc.elements || []).findIndex((rel) => rel.id === targetElementId);
            if (rSubIdx !== -1) {
              foundInRow = true;
              if (position === 'top') {
                rc.elements.splice(rSubIdx, 0, extractedEl);
                toast.success('Moved element above');
              } else if (position === 'bottom') {
                rc.elements.splice(rSubIdx + 1, 0, extractedEl);
                toast.success('Moved element below');
              } else if (position === 'left' || position === 'right') {
                const newRCol = {
                  id: `rcol_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
                  widthPercent: 50,
                  backgroundColor: 'transparent',
                  padding: '4px',
                  elements: [extractedEl],
                };
                const insertIdx = position === 'left' ? rcIdx : rcIdx + 1;
                el.columns.splice(insertIdx, 0, newRCol);
                const colCount = el.columns.length;
                const eachW = Math.floor(100 / colCount);
                el.columns.forEach((colItem, i) => {
                  colItem.widthPercent = i === colCount - 1 ? (100 - eachW * (colCount - 1)) : eachW;
                });
                toast.success('Arranged elements side by side in row');
              }
              break;
            }
          }
          if (foundInRow) break;
        }
      }

      if (!foundInRow) {
        tCol.elements.push(extractedEl);
        toast.success('Moved element to column');
      }
    }

    if (sColRef) cleanupRowsInColumn(sColRef);
    cleanupRowsInColumn(tCol);

    pushHistory(updatedBlocks);
    setSelectedBlockId(targetBlockId);
    setSelectedColumnId(targetColId);
    setSelectedSubElementId(extractedEl.id);
  };

  const arrangeElementsSideBySide = (blockId, colId, elId) => {
    const updatedBlocks = JSON.parse(JSON.stringify(blocks));
    const block = updatedBlocks.find((b) => b.id === blockId);
    if (!block) return;
    const col = (block.columns || []).find((c) => c.id === colId);
    if (!col || !col.elements || col.elements.length < 2) return;

    const idx = col.elements.findIndex((e) => e.id === elId);
    if (idx === -1) return;

    const partnerIdx = idx < col.elements.length - 1 ? idx + 1 : idx - 1;
    if (partnerIdx < 0 || partnerIdx >= col.elements.length) return;

    const firstIdx = Math.min(idx, partnerIdx);
    const secondIdx = Math.max(idx, partnerIdx);

    const firstEl = col.elements[firstIdx];
    const secondEl = col.elements[secondIdx];

    const sideBySideRow = {
      id: `row_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
      type: 'row',
      layout: '2-col-equal',
      backgroundColor: 'transparent',
      padding: '2px 0px',
      border: { enabled: false, color: '#e2e8f0', width: 1 },
      columns: [
        {
          id: `rcol_${Date.now()}_1`,
          widthPercent: 50,
          backgroundColor: 'transparent',
          padding: '4px',
          elements: [firstEl],
        },
        {
          id: `rcol_${Date.now()}_2`,
          widthPercent: 50,
          backgroundColor: 'transparent',
          padding: '4px',
          elements: [secondEl],
        },
      ],
    };

    col.elements.splice(secondIdx, 1);
    col.elements.splice(firstIdx, 1, sideBySideRow);

    pushHistory(updatedBlocks);
    setSelectedBlockId(blockId);
    setSelectedColumnId(colId);
    setSelectedSubElementId(firstEl.id);
    toast.success('Arranged elements side by side in row');
  };

  const unstackRow = (blockId, colId, rowId) => {
    const updatedBlocks = JSON.parse(JSON.stringify(blocks));
    const block = updatedBlocks.find((b) => b.id === blockId);
    if (!block) return;
    const col = (block.columns || []).find((c) => c.id === colId);
    if (!col || !col.elements) return;

    const rowIdx = col.elements.findIndex((el) => el.id === rowId);
    if (rowIdx === -1) return;

    const rowEl = col.elements[rowIdx];
    const allSubEls = (rowEl.columns || []).flatMap((rc) => rc.elements || []);

    col.elements.splice(rowIdx, 1, ...allSubEls);

    pushHistory(updatedBlocks);
    setSelectedBlockId(blockId);
    setSelectedColumnId(colId);
    if (allSubEls.length > 0) {
      setSelectedSubElementId(allSubEls[0].id);
    }
    toast.success('Stacked elements vertically');
  };

  const handleChangeBlockLayout = (blockId, newLayoutId) => {
    const block = blocks.find((b) => b.id === blockId);
    if (!block) return;
    if (block.type === 'columns') {
      const updatedBlock = changeBlockColumnLayout(block, newLayoutId);
      updateBlock(blockId, updatedBlock);
    } else {
      const newBlock = createColumnBlock(newLayoutId);
      const subEl = {
        ...block,
        id: `sub_${Date.now()}_0`,
      };
      newBlock.columns[0].elements = [subEl];
      const updated = blocks.map((b) => (b.id === blockId ? newBlock : b));
      pushHistory(updated);
    }
    toast.success('Column layout updated');
  };

  const handleAddElementSmart = (type) => {
    // If a column is selected, add inside that column
    if (selectedBlockId && selectedColumnId) {
      addElementToColumn(selectedBlockId, selectedColumnId, type);
      return;
    }

    // If a column block is selected without a column explicitly highlighted, add into first column
    const targetBlock = blocks.find((b) => b.id === selectedBlockId);
    if (targetBlock && targetBlock.type === 'columns' && targetBlock.columns?.length > 0) {
      addElementToColumn(selectedBlockId, targetBlock.columns[0].id, type);
      return;
    }

    // Otherwise add new block to canvas
    if (type === 'text') {
      addBlock({
        id: `block_text_${Date.now()}`,
        type: 'text',
        content: '<p style="margin: 0; font-size: 15px; color: #334155;">Click here and start typing your message...</p>',
        align: 'left',
        fontSize: 15,
        color: '#334155',
        lineHeight: '1.6',
        padding: '16px 24px',
      });
    } else if (type === 'image') {
      addBlock({
        id: `block_img_${Date.now()}`,
        type: 'image',
        url: 'https://placehold.co/600x240/e2e8f0/475569?text=Insert+Image',
        width: 480,
        align: 'center',
        alt: 'Email image',
        padding: '16px 20px',
      });
    } else if (type === 'button') {
      addBlock({
        id: `block_btn_${Date.now()}`,
        type: 'button',
        label: 'Click Here',
        url: '#',
        backgroundColor: '#2563eb',
        textColor: '#ffffff',
        align: 'center',
        fontSize: 15,
        borderRadius: 8,
        padding: '16px 24px',
      });
    } else if (type === 'divider') {
      addBlock({
        id: `block_div_${Date.now()}`,
        type: 'divider',
        color: '#e2e8f0',
        thickness: 1,
        width: 100,
        align: 'center',
        paddingTop: 24,
        paddingBottom: 24,
      });
    } else if (type === 'spacer') {
      addBlock({
        id: `block_spc_${Date.now()}`,
        type: 'spacer',
        height: 32,
      });
    }
  };

  // Insert signature into email
  const handleInsertSignature = (sig) => {
    if (!sig) return;

    // Check if signature is already in blocks to prevent accidental duplicates
    const exists = blocks.some((b) => b.type === 'signature' && b.signatureId === sig.id);
    if (exists) {
      toast.info(`Signature "${sig.name}" is already in this email!`);
      return;
    }

    const cleanHtml = (sig.html || '')
      .replace(/<head\b[^>]*>[\s\S]*?<\/head>/gi, '')
      .replace(/<title\b[^>]*>[\s\S]*?<\/title>/gi, '')
      .trim();

    const sigBlock = {
      id: `block_sig_${Date.now()}`,
      type: 'signature',
      signatureId: sig.id,
      name: sig.name,
      html: cleanHtml,
    };

    // Append right before footer if footer exists, else append at end
    const footerIdx = blocks.findIndex((b) => b.type === 'footer');
    if (footerIdx !== -1) {
      addBlock(sigBlock, footerIdx);
    } else {
      addBlock(sigBlock);
    }
    toast.success(`Signature "${sig.name}" inserted!`);
  };

  // Place cursor at the end of contentEditable text container
  const placeCursorAtEnd = (el) => {
    if (!el) return;
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && !sel.isCollapsed && el.contains(sel.anchorNode)) {
      return; // Do not collapse existing user selection!
    }
    try {
      el.focus();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(range);
      }
      savedRangeRef.current = range;
    } catch (err) {}
  };

  // Text selection tracking
  const handleSaveSelection = () => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0) {
      const range = sel.getRangeAt(0);
      try {
        savedRangeRef.current = range.cloneRange();
      } catch (e) {
        savedRangeRef.current = range;
      }
      let node = range.commonAncestorContainer;
      while (node && (!node.getAttribute || node.getAttribute('contenteditable') !== 'true')) {
        node = node.parentNode;
      }
      if (node) {
        activeTextElRef.current = node;
      }
    }
  };

  const getEffectiveRange = () => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0) {
      const r = sel.getRangeAt(0);
      if (!r.collapsed) return r;
    }
    if (savedRangeRef.current && !savedRangeRef.current.collapsed) {
      if (savedRangeRef.current.commonAncestorContainer?.isConnected) {
        try {
          if (sel) {
            sel.removeAllRanges();
            sel.addRange(savedRangeRef.current);
          }
          return savedRangeRef.current;
        } catch (e) {}
      }
    }
    return null;
  };

  const restoreSelection = () => {
    const r = getEffectiveRange();
    if (r) {
      try {
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
      } catch (e) {}
    }
  };

  const applySpanStyle = (range, styles) => {
    if (!range) return;
    try {
      // 1. If selection is inside an <a> tag, ensure the <a> tag inherits or adopts the style without underline
      let common = range.commonAncestorContainer;
      let parentA = common.nodeType === Node.ELEMENT_NODE ? common.closest('a') : common.parentElement?.closest('a');
      if (parentA) {
        parentA.style.textDecoration = 'none';
        if (styles.color) parentA.style.color = styles.color;
        if (styles.fontSize) parentA.style.fontSize = styles.fontSize;
        if (styles.fontFamily) parentA.style.fontFamily = styles.fontFamily;
      }

      const span = document.createElement('span');
      Object.assign(span.style, styles);
      const contents = range.extractContents();

      // Normalize any <a> tags inside extracted contents
      if (contents.querySelectorAll) {
        contents.querySelectorAll('a').forEach((a) => {
          a.style.textDecoration = 'none';
          if (styles.color) a.style.color = 'inherit';
        });
      }

      span.appendChild(contents);
      range.insertNode(span);

      // Reselect the new span so user sees it highlighted and can format further
      const sel = window.getSelection();
      if (sel) {
        const newRange = document.createRange();
        newRange.selectNodeContents(span);
        sel.removeAllRanges();
        sel.addRange(newRange);
        savedRangeRef.current = newRange;
      }

      // Find host contenteditable and sync
      let el = span.closest('[contenteditable="true"]');
      if (el) {
        activeTextElRef.current = el;
        const bId = el.dataset.blockId;
        const cId = el.dataset.colId;
        const sId = el.dataset.subId;
        if (bId && cId && sId) {
          updateSubElement(bId, cId, sId, { content: el.innerHTML });
        } else if (bId) {
          updateBlock(bId, { content: el.innerHTML });
        }
      }
    } catch (err) {
      console.error('applySpanStyle error:', err);
    }
  };

  const handleFormatText = (cmd, val = null) => {
    const effectiveRange = getEffectiveRange();
    const hasSelection = effectiveRange && !effectiveRange.collapsed;

    if (cmd === 'insertLinkCustom') {
      const { type, url, label } = val || {};
      if (url) {
        let finalUrl = url.trim();
        if (type === 'website' && !/^(https?:\/\/|mailto:|tel:|#|\/)/i.test(finalUrl)) {
          finalUrl = `https://${finalUrl}`;
        } else if (type === 'email' && !/^mailto:/i.test(finalUrl)) {
          finalUrl = `mailto:${finalUrl}`;
        }
        const textToDisplay = (label || '').trim() || (type === 'email' ? finalUrl.replace(/^mailto:/i, '') : finalUrl);

        const a = document.createElement('a');
        a.href = finalUrl;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.textContent = textToDisplay;
        a.style.color = 'inherit';
        a.style.textDecoration = 'none';
        a.style.cursor = 'pointer';

        if (hasSelection) {
          effectiveRange.deleteContents();
          effectiveRange.insertNode(a);
          effectiveRange.setStartAfter(a);
          effectiveRange.collapse(true);
          const sel = window.getSelection();
          if (sel) {
            sel.removeAllRanges();
            sel.addRange(effectiveRange);
            savedRangeRef.current = effectiveRange;
          }
        } else if (activeTextElRef.current) {
          activeTextElRef.current.appendChild(a);
          activeTextElRef.current.appendChild(document.createTextNode(' '));
        } else if (selectedSubElementId && selectedColumnId && selectedBlockId) {
          const block = blocks.find((b) => b.id === selectedBlockId);
          const col = block?.columns?.find((c) => c.id === selectedColumnId);
          const sub = col?.elements?.find((e) => e.id === selectedSubElementId);
          if (sub && sub.type === 'text') {
            const linkHtml = `<a href="${finalUrl}" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: none;">${textToDisplay}</a>`;
            const updated = (sub.content || '').trim() ? `${sub.content} ${linkHtml} ` : `<p>${linkHtml}</p>`;
            updateSubElement(selectedBlockId, selectedColumnId, selectedSubElementId, { content: updated });
          }
        } else if (selectedBlockId) {
          const block = blocks.find((b) => b.id === selectedBlockId);
          if (block && block.type === 'text') {
            const linkHtml = `<a href="${finalUrl}" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: none;">${textToDisplay}</a>`;
            const updated = (block.content || '').trim() ? `${block.content} ${linkHtml} ` : `<p>${linkHtml}</p>`;
            updateBlock(selectedBlockId, { content: updated });
          }
        }

        if (activeTextElRef.current) {
          const bId = activeTextElRef.current.dataset.blockId;
          const cId = activeTextElRef.current.dataset.colId;
          const sId = activeTextElRef.current.dataset.subId;
          if (bId && cId && sId) {
            updateSubElement(bId, cId, sId, { content: activeTextElRef.current.innerHTML });
          } else if (bId) {
            updateBlock(bId, { content: activeTextElRef.current.innerHTML });
          }
        }
        toast.success(type === 'phone' ? `Added mobile link ${textToDisplay}` : (type === 'email' ? `Added mail link ${textToDisplay}` : `Added link "${textToDisplay}"`));
      }
    } else if (cmd === 'textBoxBackground') {
      const bg = val || 'transparent';
      if (selectedSubElementId && selectedColumnId && selectedBlockId) {
        updateSubElement(selectedBlockId, selectedColumnId, selectedSubElementId, { backgroundColor: bg });
      } else if (selectedBlockId) {
        updateBlock(selectedBlockId, { backgroundColor: bg });
      }
      toast.success(bg === 'transparent' ? 'Text box background cleared' : 'Text box background updated');
    } else if (cmd === 'highlightCustom') {
      const color = val || '#fef08a';
      if (color === 'transparent') {
        document.execCommand('removeFormat', false, null);
      } else if (hasSelection) {
        applySpanStyle(effectiveRange, {
          backgroundColor: color,
          padding: '1px 3px',
          borderRadius: '3px',
        });
      }
    } else if (cmd === 'fontSizeCustom' || cmd === 'fontSize') {
      const formattedSize = typeof val === 'number' ? `${val}px` : (val ? (String(val).endsWith('px') ? val : `${val}px`) : '15px');
      if (hasSelection) {
        applySpanStyle(effectiveRange, { fontSize: formattedSize });
      } else {
        const numSize = parseInt(val, 10) || 15;
        if (selectedSubElementId && selectedColumnId) {
          updateSubElement(selectedBlockId, selectedColumnId, selectedSubElementId, { fontSize: numSize });
        } else if (selectedBlockId) {
          updateBlock(selectedBlockId, { fontSize: numSize });
        }
      }
    } else if (cmd === 'fontName' || cmd === 'fontFamily') {
      if (hasSelection) {
        applySpanStyle(effectiveRange, { fontFamily: val });
      } else {
        if (selectedSubElementId && selectedColumnId) {
          updateSubElement(selectedBlockId, selectedColumnId, selectedSubElementId, { fontFamily: val });
        } else if (selectedBlockId) {
          updateBlock(selectedBlockId, { fontFamily: val });
        }
      }
    } else if (cmd === 'foreColor' || cmd === 'color') {
      if (hasSelection) {
        applySpanStyle(effectiveRange, { color: val });
      } else {
        if (selectedSubElementId && selectedColumnId) {
          updateSubElement(selectedBlockId, selectedColumnId, selectedSubElementId, { color: val });
        } else if (selectedBlockId) {
          updateBlock(selectedBlockId, { color: val });
        }
      }
    } else {
      restoreSelection();
      document.execCommand(cmd, false, val);
    }

    // Sync content
    if (activeTextElRef.current) {
      const blockId = activeTextElRef.current.dataset.blockId;
      const subId = activeTextElRef.current.dataset.subId;
      const colId = activeTextElRef.current.dataset.colId;
      const htmlContent = activeTextElRef.current.innerHTML;
      if (subId && colId) {
        updateSubElement(blockId, colId, subId, { content: htmlContent });
      } else if (blockId) {
        updateBlock(blockId, { content: htmlContent });
      }
    }
  };

  const insertTokenIntoTarget = (token, targetBlockId, targetColId, targetSubId) => {
    if (!token) return;

    if (targetSubId && targetColId && targetBlockId) {
      const block = blocks.find((b) => b.id === targetBlockId);
      const col = block?.columns?.find((c) => c.id === targetColId);
      let sub = col?.elements?.find((e) => e.id === targetSubId);
      if (!sub) {
        for (const el of (col?.elements || [])) {
          if (el.type === 'row') {
            for (const rc of (el.columns || [])) {
              const found = (rc.elements || []).find((e) => e.id === targetSubId);
              if (found) {
                sub = found;
                break;
              }
            }
          }
          if (sub) break;
        }
      }
      if (sub && sub.type === 'text') {
        const updated = (sub.content || '').trim() ? `${sub.content} ${token} ` : `<p>${token}</p>`;
        updateSubElement(targetBlockId, targetColId, targetSubId, { content: updated });
        toast.success(`Inserted ${token}`);
        return;
      }
    }

    if (targetBlockId) {
      const block = blocks.find((b) => b.id === targetBlockId);
      if (block && block.type === 'text') {
        const updated = (block.content || '').trim() ? `${block.content} ${token} ` : `<p>${token}</p>`;
        updateBlock(targetBlockId, { content: updated });
        toast.success(`Inserted ${token}`);
        return;
      }
    }

    // Fallback: look for the first text block or create one
    const firstTextBlock = blocks.find((b) => b.type === 'text');
    if (firstTextBlock) {
      updateBlock(firstTextBlock.id, { content: `${firstTextBlock.content || ''} ${token} ` });
      toast.success(`Inserted ${token}`);
    } else {
      addBlock({
        id: `block_text_${Date.now()}`,
        type: 'text',
        content: `<p style="margin: 0; font-size: 15px; color: #334155;">Hello ${token},</p>`,
        align: 'left',
        fontSize: 15,
        color: '#334155',
        lineHeight: '1.6',
        padding: '16px 24px',
      });
      toast.success(`Added text block with ${token}`);
    }
  };

  const handleDropSmartTag = (e, blockId, colId = null, subId = null) => {
    e.preventDefault();
    e.stopPropagation();
    const token = e.dataTransfer.getData('smart-tag') || e.dataTransfer.getData('text/plain');
    if (!token || !token.startsWith('{{')) return;

    let range = null;
    if (document.caretRangeFromPoint) {
      range = document.caretRangeFromPoint(e.clientX, e.clientY);
    } else if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(e.clientX, e.clientY);
      if (pos) {
        range = document.createRange();
        range.setStart(pos.offsetNode, pos.offset);
        range.collapse(true);
      }
    }

    if (range) {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      range.deleteContents();
      const node = document.createTextNode(` ${token} `);
      range.insertNode(node);
      range.setStartAfter(node);
      range.collapse(true);

      const targetDiv = e.currentTarget;
      if (targetDiv) {
        const html = targetDiv.innerHTML;
        if (subId && colId) {
          updateSubElement(blockId, colId, subId, { content: html });
        } else {
          updateBlock(blockId, { content: html });
        }
      }
      toast.success(`Inserted ${token}`);
    } else {
      insertTokenIntoTarget(token, blockId, colId, subId);
    }
  };

  const handleInsertTagAtCursor = (token) => {
    restoreSelection();
    const sel = window.getSelection();
    let handled = false;

    if (sel && sel.rangeCount > 0 && !sel.isCollapsed && activeTextElRef.current?.contains(sel.anchorNode)) {
      const range = sel.getRangeAt(0);
      range.deleteContents();
      const node = document.createTextNode(` ${token} `);
      range.insertNode(node);
      range.setStartAfter(node);
      range.collapse(true);
      if (activeTextElRef.current) {
        const blockId = activeTextElRef.current.dataset.blockId;
        const subId = activeTextElRef.current.dataset.subId;
        const colId = activeTextElRef.current.dataset.colId;
        const html = activeTextElRef.current.innerHTML;
        if (subId && colId) {
          updateSubElement(blockId, colId, subId, { content: html });
        } else if (blockId) {
          updateBlock(blockId, { content: html });
        }
      }
      toast.success(`Inserted ${token}`);
      handled = true;
    }

    if (!handled) {
      insertTokenIntoTarget(token, selectedBlockId, selectedColumnId, selectedSubElementId);
    }
  };

  // Drag and drop blocks
  const handleDragStart = (e, index) => {
    setDraggedBlockIndex(index);
    e.dataTransfer.setData('text/plain', index);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e, index) => {
    e.preventDefault();
    setDragOverIndex(index);
  };

  const handleDrop = (e, targetIndex = null) => {
    e.preventDefault();
    const layoutId = e.dataTransfer.getData('text/layout-id');
    if (layoutId) {
      const newColBlock = createColumnBlock(layoutId);
      addBlock(newColBlock, targetIndex);
      return;
    }

    const smartTag = e.dataTransfer.getData('smart-tag') || e.dataTransfer.getData('text/plain');
    if (smartTag && smartTag.startsWith('{{')) {
      insertTokenIntoTarget(smartTag, selectedBlockId, selectedColumnId, selectedSubElementId);
      return;
    }

    if (draggedBlockIndex !== null && targetIndex !== null && draggedBlockIndex !== targetIndex) {
      const updated = [...blocks];
      const [moved] = updated.splice(draggedBlockIndex, 1);
      updated.splice(targetIndex, 0, moved);
      pushHistory(updated);
    }
    setDraggedBlockIndex(null);
    setDragOverIndex(null);
  };

  // Imperative handle for parent
  useImperativeHandle(ref, () => ({
    getData() {
      const html = generateEmailHtml({ blocks, globalStyles, kind });
      return {
        projectData: { version: 2, blocks, globalStyles },
        html: ensureResponsiveImages(html),
      };
    },
    loadHtml(html) {
      const parsed = parseHtmlToBlocks(html);
      pushHistory(parsed);
      markDirty();
    },
    appendHtml(html) {
      const parsed = parseHtmlToBlocks(html);
      pushHistory([...blocks, ...parsed]);
      markDirty();
    },
    insertTag(token) {
      handleInsertTagAtCursor(token);
      markDirty();
    },
    cleanStrayTags() {
      // Cleans any unclosed tags
      toast.success('Cleaned template tags');
    },
    isDirty: () => dirtyRef.current,
    markClean() {
      dirtyRef.current = false;
    },
  }));

  const renderSubElement = (subEl, subIdx, col, block, parentRow = null, rCol = null) => {
    const isSubSelected = selectedSubElementId === subEl.id;
    const isBeingDragged = draggedSubElement?.elementId === subEl.id;
    const isDropTarget = subDropTarget?.targetElementId === subEl.id;
    const dropPos = isDropTarget ? subDropTarget.position : null;

    return (
      <div
        key={subEl.id}
        draggable={true}
        onDragStart={(e) => {
          if (e.target !== e.currentTarget && !e.target.closest('[data-drag-handle="true"]')) {
            const sel = window.getSelection();
            if (sel && sel.toString().trim().length > 0) return;
          }
          activeTextElRef.current = null;
          handleSubDragStart(e, block.id, col.id, subEl);
        }}
        onDragEnd={() => {
          setDraggedSubElement(null);
          setSubDropTarget(null);
        }}
        onDragOver={(e) => handleSubDragOver(e, block.id, col.id, subEl)}
        onDrop={(e) => handleSubDrop(e, block.id, col.id, subEl)}
        onClick={(e) => {
          e.stopPropagation();
          setSelectedBlockId(block.id);
          setSelectedColumnId(col.id);
          setSelectedSubElementId(subEl.id);
        }}
        className={`relative group/sub mb-1.5 p-1 rounded-lg transition-all ${
          isSubSelected ? 'ring-2 ring-indigo-500 bg-indigo-50/20' : 'hover:ring-1 hover:ring-indigo-300'
        } ${isBeingDragged ? 'opacity-40 scale-[0.98]' : ''}`}
      >
        {/* Drop Position Indicators */}
        {isDropTarget && dropPos === 'top' && (
          <div className="absolute top-0 left-0 right-0 h-2 bg-blue-500 rounded-t z-30 shadow-md animate-pulse pointer-events-none select-none flex items-center justify-center">
            <span className="bg-blue-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded shadow -translate-y-2 flex items-center gap-1">
              <ArrowUp className="w-2.5 h-2.5" /> Move Here (Above)
            </span>
          </div>
        )}
        {isDropTarget && dropPos === 'bottom' && (
          <div className="absolute bottom-0 left-0 right-0 h-2 bg-blue-500 rounded-b z-30 shadow-md animate-pulse pointer-events-none select-none flex items-center justify-center">
            <span className="bg-blue-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded shadow translate-y-2 flex items-center gap-1">
              <ArrowDown className="w-2.5 h-2.5" /> Move Here (Below)
            </span>
          </div>
        )}
        {isDropTarget && dropPos === 'left' && (
          <div className="absolute left-0 top-0 bottom-0 w-2.5 bg-indigo-500 rounded-l z-30 shadow-md animate-pulse pointer-events-none select-none flex items-center">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 bg-indigo-600 text-white text-[10px] font-bold px-2 py-1 rounded shadow-md whitespace-nowrap pointer-events-none select-none flex items-center gap-1">
              <Columns2 className="w-3 h-3" /> Arrange Side-by-Side (Left)
            </span>
          </div>
        )}
        {isDropTarget && dropPos === 'right' && (
          <div className="absolute right-0 top-0 bottom-0 w-2.5 bg-indigo-500 rounded-r z-30 shadow-md animate-pulse pointer-events-none select-none flex items-center justify-end">
            <span className="absolute right-3 top-1/2 -translate-y-1/2 bg-indigo-600 text-white text-[10px] font-bold px-2 py-1 rounded shadow-md whitespace-nowrap pointer-events-none select-none flex items-center gap-1">
              <Columns2 className="w-3 h-3" /> Arrange Side-by-Side (Right)
            </span>
          </div>
        )}

        {/* Floating Sub-element Action Bar on Hover / Selection */}
        <div
          className={`absolute right-1 -top-3.5 z-20 flex items-center gap-0.5 bg-slate-800 text-white px-1.5 py-0.5 rounded-md shadow-md text-xs transition-opacity ${
            isSubSelected ? 'opacity-100' : 'opacity-0 group-hover/sub:opacity-100'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Drag Handle */}
          <div
            data-drag-handle="true"
            draggable={true}
            onDragStart={(e) => {
              e.stopPropagation();
              activeTextElRef.current = null;
              if (window.getSelection) window.getSelection().removeAllRanges();
              handleSubDragStart(e, block.id, col.id, subEl);
            }}
            className="p-1 text-slate-300 hover:text-white cursor-grab active:cursor-grabbing hover:bg-slate-700 rounded transition flex items-center"
            title="Drag to arrange side-by-side or move"
          >
            <GripVertical className="w-3 h-3" />
          </div>

          {/* Move Up in same column */}
          {!parentRow && (col.elements || []).length > 1 && subIdx > 0 && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                moveSubElementInColumn(block.id, col.id, subEl.id, -1);
              }}
              className="p-1 text-slate-300 hover:text-white hover:bg-slate-700 rounded transition flex items-center"
              title="Move Up"
            >
              <ArrowUp className="w-3 h-3" />
            </button>
          )}

          {/* Move Down in same column */}
          {!parentRow && (col.elements || []).length > 1 && subIdx < (col.elements || []).length - 1 && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                moveSubElementInColumn(block.id, col.id, subEl.id, 1);
              }}
              className="p-1 text-slate-300 hover:text-white hover:bg-slate-700 rounded transition flex items-center"
              title="Move Down"
            >
              <ArrowDown className="w-3 h-3" />
            </button>
          )}

          {/* If vertically stacked with multiple elements, provide 1-click Side-by-Side */}
          {!parentRow && (col.elements || []).length > 1 && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                arrangeElementsSideBySide(block.id, col.id, subEl.id);
              }}
              className="px-1.5 py-0.5 text-indigo-300 hover:text-white hover:bg-slate-700 rounded transition flex items-center gap-1 font-bold cursor-pointer"
              title="Arrange side-by-side in same column"
            >
              <Columns2 className="w-3 h-3 text-indigo-400" />
              <span className="text-[9px]">Side-by-Side</span>
            </button>
          )}

          {/* If inside a side-by-side row, provide 1-click Stack Vertically */}
          {parentRow && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                unstackRow(block.id, col.id, parentRow.id);
              }}
              className="px-1.5 py-0.5 text-amber-300 hover:text-white hover:bg-slate-700 rounded transition flex items-center gap-1 font-bold cursor-pointer"
              title="Stack vertically in column"
            >
              <Rows2 className="w-3 h-3 text-amber-400" />
              <span className="text-[9px]">Stack</span>
            </button>
          )}

          {/* Delete element */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              deleteBlock(block.id, col.id, subEl.id);
            }}
            className="p-1 text-rose-300 hover:text-white hover:bg-rose-600 rounded transition flex items-center cursor-pointer"
            title="Delete"
          >
            <Trash2 className="w-2.5 h-2.5" />
          </button>
        </div>

        {/* Content by Type */}
        {subEl.type === 'text' && (
          <div
            data-block-id={block.id}
            data-col-id={col.id}
            data-sub-id={subEl.id}
            contentEditable={true}
            suppressContentEditableWarning={true}
            onFocus={(e) => {
              activeTextElRef.current = e.currentTarget;
              setSelectedBlockId(block.id);
              setSelectedColumnId(col.id);
              setSelectedSubElementId(subEl.id);
              const sel = window.getSelection();
              if (!sel || sel.isCollapsed || !e.currentTarget.contains(sel.anchorNode)) {
                if (lastFocusedElRef.current !== e.currentTarget) {
                  placeCursorAtEnd(e.currentTarget);
                  lastFocusedElRef.current = e.currentTarget;
                }
              }
              handleSaveSelection();
            }}
            onClick={() => handleSaveSelection()}
            onSelect={(e) => {
              activeTextElRef.current = e.currentTarget;
              handleSaveSelection();
            }}
            onKeyUp={handleSaveSelection}
            onMouseUp={handleSaveSelection}
            onDragOver={(e) => {
              if (draggedSubElement) {
                handleSubDragOver(e, block.id, col.id, subEl);
                return;
              }
              e.preventDefault();
              e.dataTransfer.dropEffect = 'copy';
            }}
            onDrop={(e) => {
              if (draggedSubElement) {
                handleSubDrop(e, block.id, col.id, subEl);
                return;
              }
              handleDropSmartTag(e, block.id, col.id, subEl.id);
            }}
            onBlur={(e) => {
              const newHtml = e.currentTarget.innerHTML;
              if (newHtml !== (subEl.content || '')) {
                updateSubElement(block.id, col.id, subEl.id, {
                  content: newHtml,
                });
              }
            }}
            dangerouslySetInnerHTML={{ __html: subEl.content || '<p>Text...</p>' }}
            style={{
              fontFamily: subEl.fontFamily || undefined,
              textAlign: subEl.align || 'left',
              fontSize: `${subEl.fontSize || 14}px`,
              color: subEl.color || '#334155',
              lineHeight: subEl.lineHeight || '1.6',
              backgroundColor: subEl.backgroundColor || 'transparent',
              padding: subEl.padding || (subEl.backgroundColor && subEl.backgroundColor !== 'transparent' ? '10px 14px' : '4px 8px'),
              borderRadius: subEl.borderRadius !== undefined ? `${subEl.borderRadius}px` : '6px',
              border: subEl.border?.enabled ? `${subEl.border.width || 1}px solid ${subEl.border.color || '#e2e8f0'}` : 'none',
              outline: 'none',
              transition: 'background-color 0.15s ease',
            }}
          />
        )}

        {subEl.type === 'image' && (
          <div
            style={{
              textAlign: subEl.align || 'center',
              backgroundColor: subEl.backgroundColor || 'transparent',
              padding: subEl.padding || '6px',
              border: subEl.border?.enabled ? `${subEl.border.width}px solid ${subEl.border.color}` : 'none',
            }}
          >
            <img
              src={resolveImageUrl(subEl.url)}
              alt={subEl.alt || ''}
              style={{
                maxWidth: `${subEl.width || 240}px`,
                width: '100%',
                height: 'auto',
                display: 'inline-block',
                borderRadius: '4px',
              }}
            />
          </div>
        )}

        {subEl.type === 'button' && (
          <div style={{ textAlign: subEl.align || 'center' }}>
            <span
              style={{
                display: 'inline-block',
                backgroundColor: subEl.backgroundColor || '#2563eb',
                color: subEl.textColor || '#ffffff',
                padding: '8px 18px',
                borderRadius: '6px',
                fontSize: '13px',
                fontWeight: 'bold',
              }}
            >
              {subEl.label || 'Click'}
            </span>
          </div>
        )}

        {subEl.type === 'divider' && (
          <div
            style={{
              paddingTop: `${subEl.paddingTop ?? 10}px`,
              paddingBottom: `${subEl.paddingBottom ?? 10}px`,
              backgroundColor: subEl.backgroundColor || 'transparent',
            }}
          >
            <hr
              style={{
                border: 'none',
                borderTop: `${subEl.thickness || 1}px solid ${subEl.color || '#e2e8f0'}`,
                width: `${subEl.width || 100}%`,
                margin: '0 auto',
              }}
            />
          </div>
        )}

        {subEl.type === 'spacer' && (
          <div
            style={{
              height: `${subEl.height || 20}px`,
              backgroundColor: subEl.backgroundColor && subEl.backgroundColor !== 'transparent' ? subEl.backgroundColor : 'rgba(241, 245, 249, 0.4)',
              border: '1px dashed #cbd5e1',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#94a3b8',
              fontSize: '10px',
            }}
          >
            Spacer ({subEl.height || 20}px)
          </div>
        )}
      </div>
    );
  };

  const selectedBlock = blocks.find((b) => b.id === selectedBlockId) || null;

  return (
    <div className="flex flex-col border border-slate-200 rounded-2xl overflow-hidden bg-slate-100 shadow-sm">
      {/* 1. TOP TOOLBAR */}
      <div className="bg-white border-b border-slate-200 px-4 py-2.5 flex flex-wrap items-center justify-between gap-2 z-20">
        {/* Left: Undo/Redo & Add Elements */}
        <div className="flex flex-wrap items-center gap-1.5">
          {/* Undo / Redo */}
          <div className="flex items-center gap-0.5 pr-2 border-r border-slate-200">
            <button
              type="button"
              disabled={historyIdx <= 0}
              onClick={handleUndo}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-white transition"
              title="Undo (Ctrl+Z)"
            >
              <Undo2 className="w-4 h-4" />
            </button>
            <button
              type="button"
              disabled={historyIdx >= history.length - 1}
              onClick={handleRedo}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-white transition"
              title="Redo (Ctrl+Y)"
            >
              <Redo2 className="w-4 h-4" />
            </button>
          </div>

          {/* Add Text */}
          <button
            type="button"
            onClick={() => handleAddElementSmart('text')}
            className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:border-blue-400 bg-white hover:bg-blue-50 text-slate-700 hover:text-blue-700 text-xs font-bold flex items-center gap-1.5 transition cursor-pointer"
            title="Add text inside selected block/column or as a new block"
          >
            <Type className="w-3.5 h-3.5 text-blue-600" />
            <span>Add Text</span>
          </button>

          {/* Add Image */}
          <button
            type="button"
            onClick={() => handleAddElementSmart('image')}
            className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:border-emerald-400 bg-white hover:bg-emerald-50 text-slate-700 hover:text-emerald-700 text-xs font-bold flex items-center gap-1.5 transition cursor-pointer"
            title="Add image inside selected block/column or as a new block"
          >
            <ImageIcon className="w-3.5 h-3.5 text-emerald-600" />
            <span>Add Image</span>
          </button>

          {/* Add Button */}
          <button
            type="button"
            onClick={() => handleAddElementSmart('button')}
            className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:border-indigo-400 bg-white hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 text-xs font-bold flex items-center gap-1.5 transition cursor-pointer"
            title="Add button inside selected block/column or as a new block"
          >
            <MousePointerClick className="w-3.5 h-3.5 text-indigo-600" />
            <span>Add Button</span>
          </button>

          {/* Add Divider */}
          <button
            type="button"
            onClick={() => handleAddElementSmart('divider')}
            className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:border-slate-400 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-1.5 transition cursor-pointer"
            title="Add divider inside selected block/column or as a new block"
          >
            <Minus className="w-3.5 h-3.5 text-slate-500" />
            <span>Divider</span>
          </button>

          {/* Add Spacer */}
          <button
            type="button"
            onClick={() => handleAddElementSmart('spacer')}
            className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:border-slate-400 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-1.5 transition cursor-pointer"
            title="Add spacer inside selected block/column or as a new block"
          >
            <Space className="w-3.5 h-3.5 text-slate-500" />
            <span>Spacer</span>
          </button>

          {/* Add Columns Dropdown Toggle */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowColumnPicker(!showColumnPicker)}
              className="px-2.5 py-1.5 rounded-xl border border-blue-200 bg-blue-50/60 hover:bg-blue-100 text-blue-700 text-xs font-bold flex items-center gap-1.5 transition cursor-pointer"
              title="Add multi-column layout"
            >
              <Columns2 className="w-3.5 h-3.5" />
              <span>Add Columns</span>
            </button>

            {showColumnPicker && (
              <div className="absolute left-0 top-full mt-2 z-50">
                <ColumnLayoutPicker
                  onSelectLayout={(layoutId) => {
                    const newColBlock = createColumnBlock(layoutId);
                    addBlock(newColBlock);
                    setShowColumnPicker(false);
                  }}
                  onClose={() => setShowColumnPicker(false)}
                />
              </div>
            )}
          </div>

          {/* Add Signature Menu */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowInsertSigMenu(!showInsertSigMenu)}
              className="px-2.5 py-1.5 rounded-xl border border-indigo-200 bg-indigo-50/60 hover:bg-indigo-100 text-indigo-700 text-xs font-bold flex items-center gap-1.5 transition cursor-pointer"
              title="Insert a saved signature"
            >
              <PenTool className="w-3.5 h-3.5" />
              <span>Add Signature</span>
            </button>

            {showInsertSigMenu && (
              <div className="absolute left-0 top-full mt-2 w-64 p-2 bg-white rounded-2xl shadow-2xl border border-slate-200 z-50 space-y-1">
                <div className="text-[10px] font-bold text-slate-400 uppercase px-2 py-1 border-b border-slate-100">
                  Select Saved Signature
                </div>
                {savedSignatures.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-400">
                    No signatures created yet.
                  </div>
                ) : (
                  savedSignatures.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => {
                        handleInsertSignature(s);
                        setShowInsertSigMenu(false);
                      }}
                      className="w-full text-left px-2.5 py-2 rounded-xl hover:bg-indigo-50 hover:text-indigo-700 text-xs font-semibold text-slate-700 flex items-center justify-between transition cursor-pointer"
                    >
                      <span className="truncate">{s.name}</span>
                      {s.is_default && (
                        <span className="text-[10px] font-bold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">
                          Default
                        </span>
                      )}
                    </button>
                  ))
                )}
                <div className="pt-1.5 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => {
                      setShowSigBuilderModal(true);
                      setShowInsertSigMenu(false);
                    }}
                    className="w-full text-center py-1.5 text-xs font-bold text-indigo-600 hover:bg-indigo-50 rounded-xl transition cursor-pointer"
                  >
                    + Create New Signature
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Preview & Import Actions */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            id="editor-import-html-btn"
            onClick={() => {
              setImportHtmlInput('');
              setPreviewModal({ mobile: false, source: true, tab: 'import' });
            }}
            className="px-3 py-1.5 text-xs font-bold border border-emerald-200 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-800 flex items-center gap-1.5 shadow-2xs transition cursor-pointer"
            title="Import raw HTML into template canvas"
          >
            <FileCode className="w-3.5 h-3.5 text-emerald-600" />
            <span>Import HTML</span>
          </button>

          <button
            type="button"
            id="editor-html-source-btn"
            onClick={() => setPreviewModal({ mobile: false, source: true, tab: 'view' })}
            className="px-3 py-1.5 text-xs font-bold border border-slate-200 rounded-xl bg-white hover:bg-slate-50 text-slate-700 flex items-center gap-1.5 shadow-2xs transition cursor-pointer"
            title="Inspect final HTML"
          >
            <Code2 className="w-3.5 h-3.5 text-slate-500" />
            <span>HTML</span>
          </button>

          <button
            type="button"
            id="editor-live-preview-btn"
            onClick={() => setPreviewModal({ mobile: false, source: false, tab: 'preview' })}
            className="px-3 py-1.5 text-xs font-bold border border-slate-200 rounded-xl bg-white hover:bg-slate-50 text-slate-700 flex items-center gap-1.5 shadow-2xs transition cursor-pointer"
            title="Preview email on Desktop & Mobile"
          >
            <Eye className="w-3.5 h-3.5 text-blue-600" />
            <span>Preview</span>
          </button>
        </div>
      </div>

      {/* 2. SMART PERSONALIZATION TAGS STRIP */}
      <div className="bg-gradient-to-r from-indigo-50/90 via-sky-50/80 to-blue-50/90 border-b border-indigo-100 px-4 py-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
          <Sparkles className="w-4 h-4 text-indigo-600" />
          <span>Smart Personalization Tags:</span>
          <span className="text-[11px] font-normal text-slate-500 hidden sm:inline">
            (click to insert into active text or drag & drop)
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {SMART_TAGS.map((tag) => (
            <button
              key={tag.key}
              type="button"
              draggable={true}
              onDragStart={(e) => {
                e.dataTransfer.setData('text/plain', tag.token);
                e.dataTransfer.setData('smart-tag', tag.token);
                e.dataTransfer.effectAllowed = 'copy';
              }}
              onClick={() => handleInsertTagAtCursor(tag.token)}
              className={`px-2.5 py-1 rounded-lg border text-xs font-bold flex items-center gap-1 transition shadow-2xs hover:scale-105 active:scale-95 cursor-grab active:cursor-grabbing select-none ${tag.color}`}
              title={`${tag.desc} — Click to insert or drag into text`}
            >
              <GripVertical className="w-2.5 h-2.5 opacity-40 -mr-0.5" />
              <span>{tag.icon}</span>
              <span>{tag.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 3. MAIN EDITOR WORKSPACE (Canvas + Properties Panel) */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden" style={{ minHeight: height }}>
        {/* Main Canvas Scroll Area */}
        <div
          className="flex-1 p-6 overflow-y-auto flex flex-col items-center bg-slate-200/70"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setSelectedBlockId(null);
              setSelectedColumnId(null);
              setSelectedSubElementId(null);
            }
          }}
        >
          {/* Floating Rich Text Toolbar when text block is selected */}
          {(() => {
            let activeTextElement = selectedBlock?.type === 'text' ? selectedBlock : null;
            if (!activeTextElement && selectedBlock?.type === 'columns' && selectedSubElementId) {
              for (const c of (selectedBlock.columns || [])) {
                const el = (c.elements || []).find((e) => e.id === selectedSubElementId);
                if (el && el.type === 'text') {
                  activeTextElement = el;
                  break;
                }
              }
            }
            if (!activeTextElement) return null;
            return (
              <div className="sticky top-2 z-40 mb-3 animate-fade-in">
                <RichTextToolbar
                  onFormat={handleFormatText}
                  onInsertTag={handleInsertTagAtCursor}
                  currentFontFamily={activeTextElement.fontFamily}
                  currentFontSize={activeTextElement.fontSize ? `${activeTextElement.fontSize}px` : undefined}
                />
              </div>
            );
          })()}

          {/* Centered Email Canvas Container (600px) */}
          <div
            className="w-full max-w-[600px] min-h-[640px] flex flex-col justify-start bg-white rounded-xl shadow-xl border border-slate-300 overflow-hidden transition-all duration-200"
            style={{ backgroundColor: globalStyles.canvasColor || '#ffffff' }}
            onDragOver={(e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = 'copy';
            }}
            onDrop={(e) => handleDrop(e)}
          >
            {blocks.length === 0 ? (
              <div className="p-8 text-center text-slate-400 space-y-4 my-auto">
                <div className="space-y-1">
                  <h3 className="text-xs font-black tracking-wider text-slate-700 uppercase">
                    BLANK COLUMNS
                  </h3>
                  <p className="text-xs text-slate-500">
                    Click to start or drag columns into your email canvas
                  </p>
                </div>

                <div className="grid grid-cols-4 gap-2.5 max-w-sm mx-auto pt-1">
                  {COLUMN_LAYOUTS.map((layout) => (
                    <div
                      key={layout.id}
                      draggable={true}
                      onDragStart={(e) => {
                        e.dataTransfer.setData('text/layout-id', layout.id);
                        e.dataTransfer.effectAllowed = 'copy';
                      }}
                      onClick={() => {
                        const newColBlock = createColumnBlock(layout.id);
                        addBlock(newColBlock);
                      }}
                      className="aspect-square bg-slate-50 hover:bg-white border border-slate-200 hover:border-blue-500 hover:shadow-md rounded-xl p-2 flex flex-col items-center justify-center gap-1.5 cursor-pointer transition group"
                      title={`Add ${layout.name}`}
                    >
                      <div className="w-10 h-5 flex items-center gap-0.5 px-0.5">
                        {layout.boxes.map((b, i) => (
                          <div
                            key={i}
                            style={{ flex: b.flex }}
                            className="h-full border border-slate-600 rounded-[2px] bg-white group-hover:border-blue-600 group-hover:bg-blue-50 transition-colors"
                          />
                        ))}
                      </div>
                      <span className="text-[11px] font-bold text-slate-700 group-hover:text-blue-600">
                        {layout.label}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="pt-2 flex items-center justify-center gap-2 text-xs text-slate-500">
                  <span>Or start with:</span>
                  <button
                    type="button"
                    onClick={() => handleAddElementSmart('text')}
                    className="text-blue-600 font-bold hover:underline cursor-pointer"
                  >
                    + Text
                  </button>
                  <span>•</span>
                  <button
                    type="button"
                    onClick={() => handleAddElementSmart('image')}
                    className="text-emerald-600 font-bold hover:underline cursor-pointer"
                  >
                    + Image
                  </button>
                  <span>•</span>
                  <button
                    type="button"
                    onClick={() => handleAddElementSmart('button')}
                    className="text-indigo-600 font-bold hover:underline cursor-pointer"
                  >
                    + Button
                  </button>
                  <span>•</span>
                  <button
                    type="button"
                    onClick={() => {
                      setImportHtmlInput('');
                      setPreviewModal({ mobile: false, source: true, tab: 'import' });
                    }}
                    className="text-emerald-700 font-bold hover:underline cursor-pointer inline-flex items-center gap-1"
                  >
                    <FileCode className="w-3.5 h-3.5 text-emerald-600" /> Import HTML
                  </button>
                </div>
              </div>
            ) : (
              blocks.map((block, index) => {
                const isSelected = selectedBlockId === block.id && !selectedSubElementId;
                const isDragOver = dragOverIndex === index;

                return (
                  <div
                    key={block.id}
                    draggable={true}
                    onDragStart={(e) => handleDragStart(e, index)}
                    onDragOver={(e) => handleDragOver(e, index)}
                    onDrop={(e) => handleDrop(e, index)}
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedBlockId(block.id);
                      setSelectedColumnId(null);
                      setSelectedSubElementId(null);
                    }}
                    className={`relative group transition-all duration-150 ${
                      isSelected
                        ? 'ring-2 ring-blue-500 z-10'
                        : 'hover:ring-1 hover:ring-blue-300'
                    } ${isDragOver ? 'border-t-4 border-blue-500' : ''}`}
                  >
                    {/* Floating Block Actions Bar on Hover / Selection */}
                    <div
                      className={`absolute right-2 ${index === 0 ? 'top-2' : '-top-3.5'} z-30 flex items-center gap-0.5 bg-slate-800 text-white p-1 rounded-lg shadow-md text-xs transition-opacity ${
                        isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                      }`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {/* Separate into Columns Action */}
                      <button
                        type="button"
                        onClick={() => {
                          if (block.type === 'columns') {
                            const layoutOrder = ['1-col', '2-col-equal', '3-col-equal', '2-col-1-2', '2-col-2-1', '2-col-1-3', '2-col-3-1', '4-col-equal'];
                            const curIdx = layoutOrder.indexOf(block.layoutId || '2-col-equal');
                            const nextLayout = layoutOrder[(curIdx + 1) % layoutOrder.length];
                            handleChangeBlockLayout(block.id, nextLayout);
                          } else {
                            handleChangeBlockLayout(block.id, '2-col-equal');
                          }
                        }}
                        className="px-1.5 py-1 hover:bg-slate-700 rounded-md transition flex items-center gap-1 text-[11px] font-bold text-blue-300 hover:text-white"
                        title={block.type === 'columns' ? 'Separate / Cycle Columns' : 'Separate into Columns'}
                      >
                        <Columns2 className="w-3 h-3 text-blue-400" />
                        <span>Separate</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => moveBlock(index, -1)}
                        disabled={index === 0}
                        className="p-1 hover:bg-slate-700 disabled:opacity-30 rounded-md transition"
                        title="Move Up"
                      >
                        <ArrowUp className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveBlock(index, 1)}
                        disabled={index === blocks.length - 1}
                        className="p-1 hover:bg-slate-700 disabled:opacity-30 rounded-md transition"
                        title="Move Down"
                      >
                        <ArrowDown className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => duplicateBlock(block.id)}
                        className="p-1 hover:bg-slate-700 rounded-md transition"
                        title="Duplicate"
                      >
                        <Copy className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteBlock(block.id)}
                        className="p-1 hover:bg-rose-600 text-rose-300 hover:text-white rounded-md transition"
                        title="Delete"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>

                    {/* RENDER THE BLOCK */}
                    {block.type === 'header' && (
                      <div
                        style={{
                          backgroundColor: block.backgroundColor || '#0f172a',
                          padding: block.padding || '24px',
                          textAlign: block.align || 'center',
                          border: block.border?.enabled ? `${block.border.width}px solid ${block.border.color}` : 'none',
                        }}
                      >
                        {block.logoUrl && (
                          <img
                            src={resolveImageUrl(block.logoUrl)}
                            alt="Logo"
                            style={{
                              width: `${block.logoWidth || 120}px`,
                              display: 'inline-block',
                              marginBottom: '10px',
                            }}
                          />
                        )}
                        {block.title && (
                          <h1
                            style={{
                              margin: 0,
                              fontSize: '22px',
                              fontWeight: 700,
                              color: block.textColor || '#fff',
                            }}
                          >
                            {block.title}
                          </h1>
                        )}
                        {block.subtitle && (
                          <p
                            style={{
                              margin: '6px 0 0 0',
                              fontSize: '14px',
                              color: block.textColor || '#fff',
                              opacity: 0.85,
                            }}
                          >
                            {block.subtitle}
                          </p>
                        )}
                      </div>
                    )}

                    {block.type === 'text' && (
                      <div
                        ref={isSelected ? activeTextElRef : undefined}
                        data-block-id={block.id}
                        contentEditable={true}
                        suppressContentEditableWarning={true}
                        onFocus={(e) => {
                          activeTextElRef.current = e.currentTarget;
                          const sel = window.getSelection();
                          if (!sel || sel.isCollapsed || !e.currentTarget.contains(sel.anchorNode)) {
                            if (lastFocusedElRef.current !== e.currentTarget) {
                              placeCursorAtEnd(e.currentTarget);
                              lastFocusedElRef.current = e.currentTarget;
                            }
                          }
                          handleSaveSelection();
                        }}
                        onClick={() => handleSaveSelection()}
                        onSelect={(e) => {
                          activeTextElRef.current = e.currentTarget;
                          handleSaveSelection();
                        }}
                        onKeyUp={handleSaveSelection}
                        onMouseUp={handleSaveSelection}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.dataTransfer.dropEffect = 'copy';
                        }}
                        onDrop={(e) => handleDropSmartTag(e, block.id)}
                        onBlur={(e) => {
                          const newHtml = e.currentTarget.innerHTML;
                          if (newHtml !== (block.content || '')) {
                            updateBlock(block.id, { content: newHtml });
                          }
                        }}
                        dangerouslySetInnerHTML={{ __html: block.content || '<p>Type here...</p>' }}
                        style={{
                          fontFamily: block.fontFamily || undefined,
                          textAlign: block.align || 'left',
                          fontSize: `${block.fontSize || 15}px`,
                          color: block.color || '#334155',
                          lineHeight: block.lineHeight || '1.6',
                          padding: block.padding || '16px 24px',
                          backgroundColor: block.backgroundColor || 'transparent',
                          border: block.border?.enabled ? `${block.border.width}px solid ${block.border.color}` : 'none',
                          outline: 'none',
                        }}
                      />
                    )}

                    {block.type === 'image' && (
                      <div
                        style={{
                          padding: block.padding || '12px',
                          textAlign: block.align || 'center',
                          backgroundColor: block.backgroundColor || 'transparent',
                          border: block.border?.enabled ? `${block.border.width}px solid ${block.border.color}` : 'none',
                        }}
                      >
                        <img
                          src={resolveImageUrl(block.url)}
                          alt={block.alt || 'Email image'}
                          style={{
                            maxWidth: `${block.width || 320}px`,
                            width: '100%',
                            height: 'auto',
                            display: 'inline-block',
                            borderRadius: '6px',
                          }}
                        />
                      </div>
                    )}

                    {block.type === 'button' && (
                      <div
                        style={{
                          padding: block.padding || '16px',
                          textAlign: block.align || 'center',
                        }}
                      >
                        <span
                          style={{
                            display: 'inline-block',
                            backgroundColor: block.backgroundColor || '#2563eb',
                            color: block.textColor || '#ffffff',
                            padding: '12px 28px',
                            borderRadius: `${block.borderRadius ?? 8}px`,
                            fontSize: `${block.fontSize || 15}px`,
                            fontWeight: 'bold',
                            cursor: 'pointer',
                          }}
                        >
                          {block.label || 'Click Here'}
                        </span>
                      </div>
                    )}

                    {block.type === 'divider' && (
                      <div
                        style={{
                          paddingTop: `${block.paddingTop ?? 24}px`,
                          paddingBottom: `${block.paddingBottom ?? 24}px`,
                          minHeight: '48px',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'center',
                          backgroundColor: block.backgroundColor || 'transparent',
                        }}
                      >
                        <hr
                          style={{
                            border: 'none',
                            borderTop: `${block.thickness || 1}px solid ${block.color || '#e2e8f0'}`,
                            width: `${block.width || 100}%`,
                            margin: '0 auto',
                          }}
                        />
                      </div>
                    )}

                    {block.type === 'spacer' && (
                      <div
                        style={{
                          height: `${block.height || 32}px`,
                          minHeight: '24px',
                          backgroundColor: block.backgroundColor && block.backgroundColor !== 'transparent' ? block.backgroundColor : 'rgba(241, 245, 249, 0.4)',
                          border: '1px dashed #cbd5e1',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: '#94a3b8',
                          fontSize: '11px',
                          fontWeight: 500,
                        }}
                      >
                        Spacer ({block.height || 32}px)
                      </div>
                    )}

                    {block.type === 'signature' && (
                      <div style={{ padding: '16px 20px' }}>
                        <div dangerouslySetInnerHTML={{ __html: block.html || '' }} />
                      </div>
                    )}

                    {block.type === 'footer' && (
                      <div
                        style={{
                          backgroundColor: block.backgroundColor || '#f8fafc',
                          color: block.textColor || '#64748b',
                          textAlign: block.align || 'center',
                          padding: block.padding || '20px',
                          borderTop: '1px solid #e2e8f0',
                        }}
                      >
                        {block.text && <p style={{ margin: '0 0 6px 0', fontSize: '12px' }}>{block.text}</p>}
                        {block.unsubscribeText && (
                          <p style={{ margin: 0, fontSize: '11px', opacity: 0.85 }}>
                            {block.unsubscribeText}{' '}
                            <span style={{ textDecoration: 'underline' }}>Unsubscribe</span>
                          </p>
                        )}
                      </div>
                    )}

                    {/* COLUMNS BLOCK WITH DROPZONES */}
                    {block.type === 'columns' && (
                      <div
                        style={{
                          padding: block.padding || '8px 16px',
                          backgroundColor: block.backgroundColor || 'transparent',
                          border: block.border?.enabled ? `${block.border.width}px solid ${block.border.color}` : 'none',
                        }}
                      >
                        <div className="flex flex-col sm:flex-row gap-3">
                          {(block.columns || []).map((col, colIdx) => {
                            const isColSelected = selectedColumnId === col.id;
                            const isColDropTarget = subDropTarget?.colId === col.id && subDropTarget?.position === 'column';
                            return (
                              <div
                                key={col.id}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedBlockId(block.id);
                                  setSelectedColumnId(col.id);
                                  setSelectedSubElementId(null);
                                }}
                                onDragOver={(e) => {
                                  e.preventDefault();
                                  if (draggedSubElement) {
                                    e.dataTransfer.dropEffect = 'move';
                                    if (!subDropTarget || subDropTarget.position === 'column') {
                                      setSubDropTarget({
                                        blockId: block.id,
                                        colId: col.id,
                                        targetElementId: null,
                                        position: 'column',
                                      });
                                    }
                                  } else {
                                    e.dataTransfer.dropEffect = 'copy';
                                  }
                                }}
                                onDragLeave={(e) => {
                                  if (!e.currentTarget.contains(e.relatedTarget)) {
                                    if (subDropTarget?.colId === col.id && subDropTarget?.position === 'column') {
                                      setSubDropTarget(null);
                                    }
                                  }
                                }}
                                onDrop={(e) => {
                                  // Check if it's a sub-element being dragged into the column
                                  const subData = e.dataTransfer.getData('text/email-subelement');
                                  const info = draggedSubElement || (subData ? JSON.parse(subData) : null);
                                  if (info) {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    moveSubElementBetweenColumns(
                                      info.blockId,
                                      info.colId,
                                      info.elementId,
                                      block.id,
                                      col.id,
                                      null,
                                      'column'
                                    );
                                    setDraggedSubElement(null);
                                    setSubDropTarget(null);
                                    return;
                                  }

                                  // Check for smart tags
                                  const tag = e.dataTransfer.getData('smart-tag') || e.dataTransfer.getData('text/plain');
                                  if (tag && tag.startsWith('{{')) {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    const textEl = (col.elements || []).find((el) => el.type === 'text');
                                    if (textEl) {
                                      insertTokenIntoTarget(tag, block.id, col.id, textEl.id);
                                    } else {
                                      const newId = `sub_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
                                      const newEl = { id: newId, type: 'text', content: `<p>${tag}</p>`, align: 'left', fontSize: 14, color: '#334155' };
                                      const updatedCols = (block.columns || []).map((c) => (c.id === col.id ? { ...c, elements: [...(c.elements || []), newEl] } : c));
                                      updateBlock(block.id, { columns: updatedCols });
                                      toast.success(`Inserted ${tag}`);
                                    }
                                  }
                                }}
                                style={{
                                  width: `${col.widthPercent}%`,
                                  backgroundColor: col.backgroundColor || 'transparent',
                                  padding: col.padding || '8px',
                                  border: col.border?.enabled
                                    ? `${col.border.width}px solid ${col.border.color}`
                                    : '1px dashed #e2e8f0',
                                }}
                                className={`rounded-xl transition min-h-[90px] flex flex-col justify-between ${
                                  isColSelected ? 'ring-2 ring-blue-400 bg-blue-50/20' : ''
                                } ${
                                  isColDropTarget ? 'ring-2 ring-blue-500 bg-blue-50/60 ring-dashed' : ''
                                }`}
                              >
                                <div>
                                  {(col.elements || []).length === 0 ? (
                                    <div className="text-center py-5 space-y-2">
                                      {isColDropTarget ? (
                                        <div className="py-4 border-2 border-dashed border-blue-400 rounded-lg bg-blue-50/80 text-blue-600 font-bold text-xs flex flex-col items-center justify-center gap-1">
                                          <span>Drop element here</span>
                                          <span className="text-[10px] text-blue-500 font-normal">Move into this column (single row, 2 columns)</span>
                                        </div>
                                      ) : (
                                        <>
                                          <span className="text-[11px] text-slate-400 font-bold block">
                                            {Math.round(col.widthPercent)}% Column
                                          </span>
                                          <div className="flex flex-wrap justify-center gap-1">
                                            <button
                                              type="button"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                addElementToColumn(block.id, col.id, 'text');
                                              }}
                                              className="px-2 py-0.5 rounded-lg border border-slate-200 text-[10px] font-bold text-slate-600 hover:bg-slate-100 transition cursor-pointer"
                                            >
                                              + Text
                                            </button>
                                            <button
                                              type="button"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                addElementToColumn(block.id, col.id, 'image');
                                              }}
                                              className="px-2 py-0.5 rounded-lg border border-slate-200 text-[10px] font-bold text-slate-600 hover:bg-slate-100 transition cursor-pointer"
                                            >
                                              + Image
                                            </button>
                                            <button
                                              type="button"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                addElementToColumn(block.id, col.id, 'button');
                                              }}
                                              className="px-2 py-0.5 rounded-lg border border-slate-200 text-[10px] font-bold text-slate-600 hover:bg-slate-100 transition cursor-pointer"
                                            >
                                              + Button
                                            </button>
                                            <button
                                              type="button"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                addElementToColumn(block.id, col.id, 'row');
                                              }}
                                              className="px-2 py-0.5 rounded-lg border border-indigo-200 text-[10px] font-bold text-indigo-700 bg-indigo-50/60 hover:bg-indigo-100 transition cursor-pointer"
                                            >
                                              + Row
                                            </button>
                                            <button
                                              type="button"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                addElementToColumn(block.id, col.id, 'divider');
                                              }}
                                              className="px-2 py-0.5 rounded-lg border border-slate-200 text-[10px] font-bold text-slate-600 hover:bg-slate-100 transition cursor-pointer"
                                            >
                                              + Divider
                                            </button>
                                            <button
                                              type="button"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                addElementToColumn(block.id, col.id, 'spacer');
                                              }}
                                              className="px-2 py-0.5 rounded-lg border border-slate-200 text-[10px] font-bold text-slate-600 hover:bg-slate-100 transition cursor-pointer"
                                            >
                                              + Spacer
                                            </button>
                                          </div>
                                        </>
                                      )}
                                    </div>
                                  ) : (
                                    col.elements.map((subEl, subIdx) => {
                                      if (subEl.type === 'row') {
                                        return (
                                          <div
                                            key={subEl.id}
                                            className="relative group/row my-2 p-1.5 rounded-lg border border-dashed border-indigo-200/90 hover:border-indigo-400 bg-indigo-50/20 transition-all"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setSelectedBlockId(block.id);
                                              setSelectedColumnId(col.id);
                                              setSelectedSubElementId(subEl.id);
                                            }}
                                          >
                                            {/* Floating row header on hover */}
                                            <div className="absolute right-2 -top-3 z-20 flex items-center gap-1 opacity-0 group-hover/row:opacity-100 bg-slate-800 text-white px-2 py-0.5 rounded shadow text-xs transition-opacity">
                                              <span className="text-[9px] font-bold text-indigo-300 flex items-center gap-1">
                                                <Columns2 className="w-3 h-3" /> Side-by-Side Row
                                              </span>
                                              <button
                                                type="button"
                                                onClick={(e) => {
                                                  e.stopPropagation();
                                                  unstackRow(block.id, col.id, subEl.id);
                                                }}
                                                className="px-1.5 py-0.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 hover:text-white text-[9px] flex items-center gap-0.5 font-bold cursor-pointer"
                                                title="Stack elements vertically in column"
                                              >
                                                <Rows2 className="w-2.5 h-2.5 text-amber-400" />
                                                <span>Stack Vertically</span>
                                              </button>
                                              <button
                                                type="button"
                                                onClick={(e) => {
                                                  e.stopPropagation();
                                                  deleteBlock(block.id, col.id, subEl.id);
                                                }}
                                                className="p-1 rounded hover:bg-rose-600 text-rose-300 hover:text-white text-[9px] cursor-pointer"
                                                title="Delete Row"
                                              >
                                                <Trash2 className="w-2.5 h-2.5" />
                                              </button>
                                            </div>

                                            <div className="flex flex-row gap-2 items-stretch w-full">
                                              {(subEl.columns || []).map((rCol) => (
                                                <div
                                                  key={rCol.id}
                                                  style={{
                                                    width: `${rCol.widthPercent || Math.round(100 / subEl.columns.length)}%`,
                                                    backgroundColor: rCol.backgroundColor || 'transparent',
                                                    padding: rCol.padding || '2px',
                                                    border: rCol.border?.enabled ? `${rCol.border.width}px solid ${rCol.border.color}` : '1px dashed #e2e8f0',
                                                    borderRadius: '6px',
                                                  }}
                                                  className="min-h-[40px] flex-1 flex flex-col justify-center"
                                                >
                                                  {(rCol.elements || []).map((rSub, rIdx) =>
                                                    renderSubElement(rSub, rIdx, col, block, subEl, rCol)
                                                  )}
                                                </div>
                                              ))}
                                            </div>
                                          </div>
                                        );
                                      }

                                      return renderSubElement(subEl, subIdx, col, block, null, null);
                                    })
                                  )}
                                </div>

                                {/* Mini Add Buttons Inside Column */}
                                {(col.elements || []).length > 0 && (
                                  <div className="pt-2 border-t border-dashed border-slate-200 mt-2 flex flex-wrap items-center justify-center gap-1 opacity-60 hover:opacity-100 transition">
                                    <span className="text-[9px] text-slate-400 font-bold mr-0.5">+ Add:</span>
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        addElementToColumn(block.id, col.id, 'text');
                                      }}
                                      className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white hover:bg-blue-50 text-slate-600 hover:text-blue-600 border border-slate-200 transition cursor-pointer"
                                    >
                                      Text
                                    </button>
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        addElementToColumn(block.id, col.id, 'image');
                                      }}
                                      className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white hover:bg-emerald-50 text-slate-600 hover:text-emerald-600 border border-slate-200 transition cursor-pointer"
                                    >
                                      Image
                                    </button>
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        addElementToColumn(block.id, col.id, 'button');
                                      }}
                                      className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white hover:bg-indigo-50 text-slate-600 hover:text-indigo-600 border border-slate-200 transition cursor-pointer"
                                    >
                                      Button
                                    </button>
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        addElementToColumn(block.id, col.id, 'row');
                                      }}
                                      className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 transition cursor-pointer"
                                    >
                                      Row
                                    </button>
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        addElementToColumn(block.id, col.id, 'divider');
                                      }}
                                      className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 transition cursor-pointer"
                                    >
                                      Divider
                                    </button>
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        addElementToColumn(block.id, col.id, 'spacer');
                                      }}
                                      className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 transition cursor-pointer"
                                    >
                                      Spacer
                                    </button>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>

                        {/* Add Row Button at bottom of Columns Block */}
                        <div className="flex items-center justify-center pt-3 border-t border-slate-100/80 mt-2">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              const newBlock = createColumnBlock(block.layout || '2-col-equal');
                              const idx = blocks.findIndex((b) => b.id === block.id);
                              addBlock(newBlock, idx !== -1 ? idx + 1 : null);
                              toast.success('Added new row block below');
                            }}
                            className="py-1 px-3.5 rounded-xl border border-dashed border-indigo-300 hover:border-indigo-500 bg-indigo-50/40 hover:bg-indigo-50 text-indigo-700 text-xs font-bold flex items-center gap-1.5 transition cursor-pointer shadow-2xs"
                            title="Add another row of columns below this block"
                          >
                            <Columns2 className="w-3.5 h-3.5" />
                            <span>+ Add Row Below This Block</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Properties Panel */}
        <div className="w-full md:w-80 bg-white border-t md:border-t-0 md:border-l border-slate-200 overflow-y-auto">
          <PropertiesPanel
            selectedBlock={selectedBlock}
            selectedColumnId={selectedColumnId}
            selectedSubElementId={selectedSubElementId}
            onUpdateBlock={updateBlock}
            onUpdateSubElement={updateSubElement}
            onUpdateColumn={updateColumn}
            onDeleteBlock={deleteBlock}
            onChangeBlockLayout={handleChangeBlockLayout}
            onAddElementToColumn={addElementToColumn}
            onOpenSignatureBuilder={() => setShowSigBuilderModal(true)}
            savedSignatures={savedSignatures}
            onFormatText={handleFormatText}
          />
        </div>
      </div>

      {/* 4. SIGNATURE BUILDER MODAL */}
      {showSigBuilderModal && (
        <SignatureBuilderModal
          onClose={() => setShowSigBuilderModal(false)}
          onSaved={(newSig) => {
            setSavedSignatures((prev) => [newSig, ...prev.filter((x) => x.id !== newSig.id)]);
            handleInsertSignature(newSig);
          }}
        />
      )}

      {/* 5. PREVIEW & HTML IMPORT/VIEW MODAL */}
      {previewModal && (
        <div className="fixed inset-0 z-[120] bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl h-[88vh] flex flex-col overflow-hidden border border-slate-200">
            {/* Top Bar */}
            <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-3">
                <h3 className="font-extrabold text-slate-800 text-sm">
                  {previewModal.source
                    ? previewModal.tab === 'import'
                      ? '📥 Import HTML Template'
                      : '📄 Email HTML Source Code'
                    : '✨ Live Email Preview'}
                </h3>
                {!previewModal.source && (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Previewing with sample customer data
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {previewModal.source ? (
                  <div className="flex items-center border border-slate-200 rounded-xl bg-white p-0.5">
                    <button
                      type="button"
                      onClick={() => setPreviewModal((p) => ({ ...p, tab: 'view' }))}
                      className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition cursor-pointer ${
                        previewModal.tab === 'view'
                          ? 'bg-blue-600 text-white shadow-2xs'
                          : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <Code2 className="w-3.5 h-3.5" />
                      <span>View HTML</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreviewModal((p) => ({ ...p, tab: 'import' }))}
                      className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition cursor-pointer ${
                        previewModal.tab === 'import'
                          ? 'bg-emerald-600 text-white shadow-2xs'
                          : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <FileCode className="w-3.5 h-3.5" />
                      <span>Import HTML</span>
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center border border-slate-200 rounded-xl bg-white p-0.5">
                    <button
                      type="button"
                      onClick={() => setPreviewModal((p) => ({ ...p, mobile: false }))}
                      className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition ${
                        !previewModal.mobile
                          ? 'bg-blue-600 text-white'
                          : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <Monitor className="w-3.5 h-3.5" />
                      <span>Desktop</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreviewModal((p) => ({ ...p, mobile: true }))}
                      className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition ${
                        previewModal.mobile
                          ? 'bg-blue-600 text-white'
                          : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <Smartphone className="w-3.5 h-3.5" />
                      <span>Mobile</span>
                    </button>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => setPreviewModal(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            {previewModal.source ? (
              previewModal.tab === 'import' ? (
                /* Import HTML Tab */
                <div className="flex-1 flex flex-col p-4 bg-slate-50 gap-3 overflow-hidden">
                  <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 px-4 py-2.5 rounded-xl text-xs flex items-start gap-2.5">
                    <FileCode className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-bold">Paste or import HTML code directly into your template canvas</p>
                      <p className="text-emerald-700 text-[11px] mt-0.5">
                        Supports full HTML documents, email newsletters, signature designs, and table snippets. Once imported, you can visually edit and customize all content on the canvas.
                      </p>
                    </div>
                  </div>
                  <textarea
                    id="import-html-textarea-canvas"
                    value={importHtmlInput}
                    onChange={(e) => setImportHtmlInput(e.target.value)}
                    placeholder="Paste your HTML code here (e.g. <table>...</table> or full <!DOCTYPE html>...)..."
                    className="flex-1 w-full p-3 font-mono text-xs bg-slate-900 text-slate-100 rounded-xl border border-slate-700 outline-none focus:ring-2 focus:ring-emerald-500 resize-none select-text"
                  />
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-xs text-slate-500">
                      {importHtmlInput ? `${importHtmlInput.length.toLocaleString()} characters` : 'No code entered yet'}
                    </span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setPreviewModal(null)}
                        className="px-3.5 py-2 text-xs font-bold text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-xl cursor-pointer transition hover:bg-slate-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        id="btn-confirm-import-html-canvas"
                        onClick={() => {
                          if (!importHtmlInput.trim()) {
                            toast.warning('Please enter or paste HTML code to import.');
                            return;
                          }
                          const parsed = parseHtmlToBlocks(importHtmlInput);
                          pushHistory(parsed);
                          setSelectedBlockId(null);
                          setSelectedColumnId(null);
                          setSelectedSubElementId(null);
                          setPreviewModal(null);
                          setImportHtmlInput('');
                          toast.success('HTML template imported successfully into canvas!');
                        }}
                        disabled={!importHtmlInput.trim()}
                        className="px-4 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 text-white rounded-xl flex items-center gap-1.5 transition cursor-pointer shadow-sm disabled:cursor-not-allowed"
                      >
                        <Upload className="w-4 h-4" />
                        <span>Import HTML into Canvas</span>
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                /* View HTML Tab */
                <div className="flex-1 flex flex-col overflow-hidden relative">
                  <div className="absolute top-3 right-3 z-10">
                    <button
                      type="button"
                      onClick={async () => {
                        const html = generateEmailHtml({ blocks, globalStyles, kind });
                        try {
                          await navigator.clipboard.writeText(html);
                          setCopiedSource(true);
                          toast.success('HTML copied to clipboard!');
                          setTimeout(() => setCopiedSource(false), 2000);
                        } catch {
                          toast.error('Failed to copy HTML');
                        }
                      }}
                      className="px-2.5 py-1.5 text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg flex items-center gap-1.5 transition cursor-pointer border border-slate-700 shadow-sm"
                    >
                      {copiedSource ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copiedSource ? 'Copied!' : 'Copy Code'}</span>
                    </button>
                  </div>
                  <pre className="flex-1 overflow-auto p-4 text-xs font-mono bg-slate-900 text-slate-100 whitespace-pre-wrap select-all">
                    {generateEmailHtml({ blocks, globalStyles, kind })}
                  </pre>
                </div>
              )
            ) : (
              /* Live Preview */
              <div className="flex-1 bg-slate-200/80 overflow-auto flex justify-center p-6">
                <iframe
                  title="Live Email Preview"
                  sandbox="allow-same-origin allow-scripts allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
                  srcDoc={fillSample(generateEmailHtml({ blocks, globalStyles, kind }))}
                  style={{
                    width: previewModal.mobile ? '375px' : '100%',
                    maxWidth: previewModal.mobile ? '375px' : '640px',
                    height: '100%',
                    backgroundColor: '#ffffff',
                    border: '1px solid #cbd5e1',
                    borderRadius: previewModal.mobile ? '24px' : '8px',
                    boxShadow: '0 15px 30px -5px rgba(0, 0, 0, 0.1)',
                  }}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export default SimpleEmailEditor;
