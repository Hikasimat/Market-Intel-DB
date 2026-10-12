import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import grapesjs from 'grapesjs';
import 'grapesjs/dist/css/grapes.min.css';
import newsletterPreset from 'grapesjs-preset-newsletter';
// Icons used by the newsletter preset panels (scoped to the editor chunk, which is lazy-loaded).
import '@fortawesome/fontawesome-free/css/fontawesome.min.css';
import '@fortawesome/fontawesome-free/css/solid.min.css';

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

    const hasProject = projectData && Array.isArray(projectData.pages) && projectData.pages.length > 0;
    if (hasProject) {
      editor.loadProjectData(projectData);
    } else if (initialHtml) {
      editor.setComponents(initialHtml);
    }

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
      editor.addComponents(html);
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
