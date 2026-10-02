(() => {
  const root = document.getElementById('study-archive');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const editor = $('study-editor'), viewer = $('study-viewer'), form = $('study-form');
  let current = null, editing = null;
  const localDate = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
  const error = (id, message = '') => { $(id).textContent = message; $(id).hidden = !message; };
  const node = (tag, text) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; return el; };
  async function api(path, body) {
    const response = await fetch('/api/study-materials' + path, {method: body ? 'POST' : 'GET', headers: body ? {'X-Study-Token': root.dataset.token} : {}, body});
    if (!response.ok) { let message = 'Could not save or load this material. Please try again.'; try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail; } catch (_) {} throw new Error(message); }
    return response.json();
  }
  function hint() {
    const value = form.elements.studied_on.value;
    if (!value) return;
    $('study-schedule-hint').textContent = 'Revision dates: ' + [3,7,15,30,60].map(offset => { const d = new Date(value+'T12:00:00'); d.setDate(d.getDate()+offset); return d.toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'}); }).join(' · ') + '. Dates stay anchored to this study date.';
  }
  function openEditor(day, entry = null) {
    editing = entry;
    form.reset();
    form.elements.title.value = entry ? entry.title : '';
    form.elements.notes.value = entry ? entry.notes : '';
    form.elements.studied_on.value = entry ? entry.studied_on : day;
    form.elements.studied_on.max = localDate();
    form.elements.studied_on.disabled = !!entry;
    form.elements.activity.value = entry ? entry.activity : 'Studied';
    form.elements.activity.disabled = !!entry;
    $('study-editor-title').textContent = entry ? 'Edit study material' : 'Add study material';
    form.querySelector('[type=submit]').textContent = entry ? 'Save changes' : 'Save material & schedule';
    error('study-form-error'); hint();
    editor.showModal();
  }
  function preview(asset) {
    const area = $('study-preview'); area.replaceChildren();
    const url = asset.url || '/api/study-materials/files/' + asset.id;
    const link = node('a', asset.url ? 'Open original website ↗' : 'Open file in a new tab ↗');
    link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; area.append(link);
    if (asset.media_type.startsWith('image/')) {
      const img = node('img'); img.alt = asset.name; img.src = url;
      img.onerror = () => { img.remove(); area.append(node('p','The image could not be loaded. Check that the file still exists in your local study folder.')); };
      area.append(img);
    } else {
      if (asset.url) {
        area.append(node('p','Some websites block embedded viewing. Use “Open original website” if the preview is blank.'));
        const button = node('button', 'Load website preview'); button.type = 'button';
        button.onclick = () => { button.remove(); embed(url, asset.name, true); }; area.append(button);
      } else embed(url, asset.name, false);
    }
  }
  function embed(url, name, external) {
    const frame = node('iframe'); frame.title = name; frame.referrerPolicy = 'no-referrer';
    if (external) frame.setAttribute('sandbox','allow-scripts allow-forms');
    frame.src = url; $('study-preview').append(frame);
  }
  function renderEntry(entry) {
    current = entry;
    $('study-view-title').textContent = entry.title;
    $('study-view-meta').textContent = `${entry.activity} ${entry.studied_on} · ${entry.assets.length} attachment(s)`;
    $('study-notes').textContent = entry.notes;
    $('study-assets').replaceChildren(); $('study-reviews').replaceChildren(); error('study-view-error');
    entry.assets.forEach(asset => { const b = node('button', (asset.url ? '↗ ' : asset.media_type === 'application/pdf' ? 'PDF · ' : 'Photo · ') + asset.name); b.type = 'button'; b.onclick = () => preview(asset); $('study-assets').append(b); });
    entry.reviews.forEach(review => {
      const row = node('div'); row.className = 'study-review';
      const text = node('span', `Day ${review.offset} · ${review.due_on}`);
      text.append(node('small', review.completed_on ? `Completed ${review.completed_on}` : review.due_on < localDate() ? 'Overdue' : review.due_on === localDate() ? 'Due today' : 'Scheduled'));
      const b = node('button', review.completed_on ? 'Undo' : 'Mark done'); b.type = 'button'; b.disabled = !review.completed_on && review.due_on > localDate();
      b.onclick = async () => { b.disabled = true; try { const body = new FormData(); body.set('done', review.completed_on ? 'false' : 'true'); const updated = await api(`/${entry.id}/reviews/${review.offset}`, body); renderEntry(updated); viewer.dataset.changed = 'true'; } catch(e) { error('study-view-error', e.message); b.disabled = false; } };
      row.append(text,b); $('study-reviews').append(row);
    });
  }
  document.addEventListener('click', async event => {
    const close = event.target.closest('[data-study-close]'); if(close) { close.closest('dialog').close(); return; }
    const add = event.target.closest('[data-study-add],[data-study-date]');
    if (add) { openEditor(add.dataset.studyDate || localDate()); return; }
    const item = event.target.closest('[data-study-id]');
    if (item) {
      error('study-page-error'); item.disabled = true;
      try { const entry = await api('/'+item.dataset.studyId); renderEntry(entry); $('study-preview').replaceChildren(); if(entry.assets.length) preview(entry.assets[0]); else $('study-preview').append(node('p','No attachments yet. Use “Edit / add attachments” to add PDFs, photos or links.')); viewer.showModal(); }
      catch(e) { error('study-page-error', e.message); } finally { item.disabled = false; }
    }
  });
  $('study-edit').onclick = () => openEditor(current.studied_on, current);
  viewer.addEventListener('close', () => { $('study-preview').replaceChildren(); if(viewer.dataset.changed) location.reload(); });
  form.elements.studied_on.addEventListener('change', hint);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const submit = form.querySelector('[type=submit]'); submit.disabled = true; error('study-form-error');
    try {
      const body = new FormData(form); body.delete('files');
      const files = Array.from(form.elements.files.files);
      if(files.some(f=>f.size>25*1024*1024) || files.reduce((sum,f)=>sum+f.size,0)>100*1024*1024) throw new Error('Files are limited to 25 MB each and 100 MB per upload.');
      files.forEach(file=>body.append('files',file));
      const result = await api(editing ? '/'+editing.id : '', body);
      const [year, month] = result.studied_on.split('-'); location.href = `/calendar?year=${year}&month=${Number(month)}`;
    } catch(e) { error('study-form-error', e.message); } finally { submit.disabled = false; }
  });
})();
