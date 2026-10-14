import React from 'react';
import { X } from 'lucide-react';

export const COLUMN_LAYOUTS = [
  {
    id: '1-col',
    label: '1',
    name: '1 Column',
    widths: [100],
    boxes: [{ flex: '1' }],
  },
  {
    id: '2-col-equal',
    label: '2',
    name: '2 Columns',
    widths: [50, 50],
    boxes: [{ flex: '1' }, { flex: '1' }],
  },
  {
    id: '3-col-equal',
    label: '3',
    name: '3 Columns',
    widths: [33.33, 33.33, 33.34],
    boxes: [{ flex: '1' }, { flex: '1' }, { flex: '1' }],
  },
  {
    id: '2-col-1-2',
    label: '1:2',
    name: '1:2 Columns',
    widths: [33.33, 66.67],
    boxes: [{ flex: '1' }, { flex: '2' }],
  },
  {
    id: '2-col-2-1',
    label: '2:1',
    name: '2:1 Columns',
    widths: [66.67, 33.33],
    boxes: [{ flex: '2' }, { flex: '1' }],
  },
  {
    id: '2-col-1-3',
    label: '1:3',
    name: '1:3 Columns',
    widths: [25, 75],
    boxes: [{ flex: '1' }, { flex: '3' }],
  },
  {
    id: '2-col-3-1',
    label: '3:1',
    name: '3:1 Columns',
    widths: [75, 25],
    boxes: [{ flex: '3' }, { flex: '1' }],
  },
  {
    id: '4-col-equal',
    label: '4',
    name: '4 Columns',
    widths: [25, 25, 25, 25],
    boxes: [{ flex: '1' }, { flex: '1' }, { flex: '1' }, { flex: '1' }],
  },
];

/**
 * Creates default column data structure for a layout
 */
export const createColumnBlock = (layoutId) => {
  const layout = COLUMN_LAYOUTS.find((l) => l.id === layoutId) || COLUMN_LAYOUTS[0];
  return {
    id: `block_col_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
    type: 'columns',
    layout: layout.id,
    padding: '12px 16px',
    backgroundColor: 'transparent',
    border: { enabled: false, color: '#e2e8f0', width: 1 },
    columns: layout.widths.map((w, idx) => ({
      id: `col_${Date.now()}_${idx}`,
      widthPercent: w,
      padding: '12px',
      backgroundColor: 'transparent',
      border: { enabled: false, color: '#e2e8f0', width: 1 },
      elements: [],
    })),
  };
};

/**
 * Changes/separates the columns structure of an existing block while preserving its elements
 */
export const changeBlockColumnLayout = (block, newLayoutId) => {
  const layout = COLUMN_LAYOUTS.find((l) => l.id === newLayoutId) || COLUMN_LAYOUTS[0];
  const targetColsCount = layout.widths.length;
  const existingCols = block.columns || [];

  const allElements = [];
  existingCols.forEach((col) => {
    (col.elements || []).forEach((el) => allElements.push(el));
  });

  const newCols = layout.widths.map((w, idx) => ({
    id: existingCols[idx]?.id || `col_${Date.now()}_${idx}`,
    widthPercent: w,
    padding: '12px',
    backgroundColor: existingCols[idx]?.backgroundColor || 'transparent',
    border: existingCols[idx]?.border || { enabled: false, color: '#e2e8f0', width: 1 },
    elements: [],
  }));

  allElements.forEach((el, elIdx) => {
    const targetColIdx = Math.min(elIdx, targetColsCount - 1);
    newCols[targetColIdx].elements.push(el);
  });

  return {
    ...block,
    layout: layout.id,
    columns: newCols,
  };
};

const ColumnLayoutPicker = ({ onSelectLayout, onClose }) => {
  return (
    <div className="p-5 bg-white rounded-2xl shadow-2xl border border-slate-200 w-80 space-y-4 select-none">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-xs font-black tracking-wider text-slate-800 uppercase">
            BLANK COLUMNS
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Drag to add columns to your email
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-2.5">
        {COLUMN_LAYOUTS.map((layout) => (
          <div
            key={layout.id}
            draggable={true}
            onDragStart={(e) => {
              e.dataTransfer.setData('text/layout-id', layout.id);
              e.dataTransfer.effectAllowed = 'copy';
            }}
            onClick={() => onSelectLayout(layout.id)}
            className="aspect-square bg-white border border-slate-200 hover:border-blue-500 hover:shadow-md rounded-xl p-2.5 flex flex-col items-center justify-center gap-2.5 cursor-pointer transition group"
            title={`Add ${layout.name}`}
          >
            {/* Box diagram matching Canva / Screenshot 1 */}
            <div className="w-12 h-6 flex items-center gap-0.5 px-0.5">
              {layout.boxes.map((b, i) => (
                <div
                  key={i}
                  style={{ flex: b.flex }}
                  className="h-full border border-slate-700 rounded-[2px] bg-white group-hover:border-blue-600 group-hover:bg-blue-50 transition-colors"
                />
              ))}
            </div>
            <span className="text-xs font-semibold text-slate-700 group-hover:text-blue-600">
              {layout.label}
            </span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-slate-400 text-center">
        Click to insert into canvas or drag directly onto email.
      </p>
    </div>
  );
};

export default ColumnLayoutPicker;
