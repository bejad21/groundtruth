import { ChangeEvent, DragEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';
import { checkHealth, confirmRecord, extractTicket } from './api/client';
import type { ExtractResponse, IntakeRecord, ToolTraceStep } from './types';
import { MATERIAL_OPTIONS } from './types';
import './styles/theme.css';

type Phase = 'empty' | 'trace' | 'review' | 'confirmed';
type FieldKey = 'material_type' | 'weight_kg' | 'source_name' | 'truck_or_driver_id' | 'delivery_date' | 'notes';

const STEP_LABELS: Record<string, { en: string; ar: string }> = {
  document_received: { en: 'Document received', ar: 'تم استلام المستند' },
  provider_call: { en: 'Calling the model', ar: 'استدعاء النموذج' },
  provider_skip: { en: 'Provider skipped', ar: 'تم تخطي المزود' },
  provider_failover: { en: 'Falling back to next provider', ar: 'الانتقال إلى المزود التالي' },
  confidence_gate: { en: 'Checking confidence scores', ar: 'فحص درجات الثقة' },
  validation: { en: 'Running validation rules', ar: 'تشغيل قواعد التحقق' },
  result: { en: 'Result ready', ar: 'النتيجة جاهزة' },
};

const copy = {
  en: {
    brand: 'GROUND / TRUTH', edition: 'OPS 01', live: 'Agent online', offline: 'Agent offline', eyebrow: 'DOCUMENT → VERIFIED RECORD',
    headlineA: 'Paper in.', headlineB: 'Clean data out.',
    intro: 'A single-agent intake workflow for agricultural waste deliveries. Drop a ticket; inspect the reasoning; approve the record.',
    queue: 'INTAKE QUEUE', queueValue: 'No documents waiting', start: 'START A RUN',
    dropTitle: 'Drop a delivery ticket here', dropSub: 'PDF, JPG or PNG · up to 8 MB', choose: 'Choose file',
    samples: 'OR TRY A FIELD SAMPLE', sampleA: 'Clean ticket', sampleB: 'Smudged ticket', sampleTag: 'SAMPLE',
    checks: 'WHAT THE AGENT CHECKS',
    checksList: ['Required fields present', 'Weight within 1–40,000 kg', 'Date not in the future', 'Confidence threshold ≥ 75%'],
    audit: 'Every decision is visible in the run trace.', traceTitle: 'Agent is reading the ticket', traceSub: 'Live run trace · groundtruth',
    preview: 'SOURCE DOCUMENT', detected: (n: number) => `${n} steps logged`, running: 'RUNNING', complete: 'DONE',
    runLabel: 'RUN', liveTrace: 'LIVE TRACE', structuredRecord: 'STRUCTURED RECORD',
    reviewEyebrow: 'HUMAN-IN-THE-LOOP REVIEW',
    reviewTitleFlagged: (n: number) => `${n} field${n === 1 ? '' : 's'} need${n === 1 ? 's' : ''} a second look.`,
    reviewTitleClean: 'Every field passed automatically.',
    reviewSubFlagged: 'Correct the highlighted values, then confirm it for intake.',
    reviewSubClean: 'The record passed all validation rules with high confidence. Review and confirm.',
    statusReview: 'Needs review', statusClean: 'Passed automatically', passed: (ok: number, total: number) => `${ok} / ${total} rules passed`, confidence: 'confidence',
    labels: { material_type: 'Material type', weight_kg: 'Net weight', source_name: 'Source / farm', truck_or_driver_id: 'Truck / driver ID', delivery_date: 'Delivery date', notes: 'Notes' } as Record<FieldKey, string>,
    kg: 'KG', low: 'CHECK', editHint: 'Low confidence — compare with ticket', confirm: 'Confirm intake record',
    confirmNote: 'This action writes the reviewed record to the intake ledger.', newRun: 'Start new run',
    confirmedEyebrow: 'RECORD ACCEPTED', confirmedTitle: 'Load cleared for intake.',
    confirmedSub: 'The reviewed record is now available to downstream operations. The source ticket and full agent trace remain attached for audit.',
    record: 'RECORD', accepted: 'Accepted', ledger: 'INTAKE LEDGER', reference: 'REFERENCE', timestamp: 'CONFIRMED AT', by: 'CONFIRMED BY', operator: 'Site operator',
    footer: 'Single-agent document intake · Demonstration environment', uploadError: 'Please choose a PDF, JPG or PNG file.',
    errorTitle: 'Something went wrong', via: 'via',
  },
  ar: {
    brand: 'GROUND / TRUTH', edition: 'تشغيل ٠١', live: 'الوكيل متصل', offline: 'الوكيل غير متصل', eyebrow: 'مستند ← سجل موثّق',
    headlineA: 'أدخل الورق.', headlineB: 'واستلم بيانات نظيفة.',
    intro: 'سير عمل ذكي لاستلام مخلفات المزارع. أرفق التذكرة، راقب خطوات التحليل، ثم اعتمد السجل.',
    queue: 'قائمة الاستلام', queueValue: 'لا توجد مستندات معلّقة', start: 'ابدأ عملية جديدة',
    dropTitle: 'أسقط تذكرة التسليم هنا', dropSub: 'PDF أو JPG أو PNG · حتى 8 ميجابايت', choose: 'اختر ملفاً',
    samples: 'أو جرّب عينة ميدانية', sampleA: 'تذكرة واضحة', sampleB: 'تذكرة غير واضحة', sampleTag: 'عينة',
    checks: 'ما الذي يتحقق منه الوكيل؟',
    checksList: ['اكتمال الحقول المطلوبة', 'الوزن بين 1 و40,000 كجم', 'التاريخ ليس في المستقبل', 'درجة الثقة 75٪ فأعلى'],
    audit: 'كل قرار ظاهر في سجل التشغيل.', traceTitle: 'الوكيل يقرأ التذكرة', traceSub: 'سجل تشغيل مباشر · Groundtruth',
    preview: 'المستند الأصلي', detected: (n: number) => `${n} خطوات مسجَّلة`, running: 'جارٍ', complete: 'تم',
    runLabel: 'التشغيل', liveTrace: 'سجل مباشر', structuredRecord: 'السجل المهيكل',
    reviewEyebrow: 'مراجعة بشرية سريعة',
    reviewTitleFlagged: (n: number) => `${n} حقل يحتاج نظرة ثانية.`,
    reviewTitleClean: 'اجتازت جميع الحقول تلقائياً.',
    reviewSubFlagged: 'صحّح القيم المميزة ثم اعتمده للاستلام.',
    reviewSubClean: 'اجتاز السجل جميع قواعد التحقق بثقة عالية. راجعه ثم اعتمده.',
    statusReview: 'يحتاج مراجعة', statusClean: 'اجتاز تلقائياً', passed: (ok: number, total: number) => `اجتاز ${ok} / ${total} قواعد`, confidence: 'درجة الثقة',
    labels: { material_type: 'نوع المادة', weight_kg: 'الوزن الصافي', source_name: 'المصدر / المزرعة', truck_or_driver_id: 'معرّف الشاحنة / السائق', delivery_date: 'تاريخ التسليم', notes: 'ملاحظات' } as Record<FieldKey, string>,
    kg: 'كجم', low: 'تحقق', editHint: 'ثقة منخفضة — قارن بالتذكرة', confirm: 'اعتماد سجل الاستلام',
    confirmNote: 'سيتم حفظ السجل المراجع في دفتر الاستلام.', newRun: 'بدء عملية جديدة',
    confirmedEyebrow: 'تم قبول السجل', confirmedTitle: 'الشحنة جاهزة للاستلام.',
    confirmedSub: 'السجل المراجع متاح الآن لفريق التشغيل. ستبقى التذكرة الأصلية وسجل الوكيل الكامل مرفقين لأغراض التدقيق.',
    record: 'السجل', accepted: 'مقبول', ledger: 'دفتر الاستلام', reference: 'المرجع', timestamp: 'وقت الاعتماد', by: 'اعتمد بواسطة', operator: 'مشغّل الموقع',
    footer: 'وكيل واحد لاستلام المستندات · بيئة تجريبية', uploadError: 'يرجى اختيار ملف PDF أو JPG أو PNG.',
    errorTitle: 'حدث خطأ ما', via: 'عبر',
  },
};

const RULE_KEYS = ['required', 'weight', 'date', 'material'];
const SAMPLE_URLS = { clean: '/samples/ticket_clean.png', messy: '/samples/ticket_messy.png' } as const;
const FIELD_KEYS: FieldKey[] = ['material_type', 'weight_kg', 'source_name', 'truck_or_driver_id', 'delivery_date', 'notes'];

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    upload: <><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/></>,
    file: <><path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5"/><path d="M9 13h6M9 17h6"/></>,
    check: <path d="m5 12 4 4L19 6"/>, arrow: <><path d="M5 12h14"/><path d="m14 7 5 5-5 5"/></>,
    rotate: <><path d="M20 7v5h-5"/><path d="M19 12a7 7 0 1 1-2-5"/></>,
    shield: <><path d="M12 3 5 6v5c0 5 3 8 7 10 4-2 7-5 7-10V6z"/><path d="m9 12 2 2 4-4"/></>,
    spark: <><path d="m12 3 1.3 4.2L17 9l-3.7 1.8L12 15l-1.3-4.2L7 9l3.7-1.8z"/><path d="m18 15 .7 2.3L21 18l-2.3.7L18 21l-.7-2.3L15 18l2.3-.7z"/></>,
  };
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function humanizeMaterial(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function snakeMaterial(value: string): string {
  return value.trim().toLowerCase().replaceAll(/\s+/g, '_');
}

function DocumentView({ previewUrl, mimeType, scanning }: { previewUrl: string | null; mimeType: string; scanning: boolean }) {
  const isImage = mimeType.startsWith('image/');
  return (
    <div className={`ticket-wrap ${scanning ? 'is-scanning' : ''}`} aria-label="Preview of the uploaded document">
      {isImage && previewUrl ? (
        <img src={previewUrl} alt="Uploaded ticket" className="doc-image" />
      ) : (
        <div className="doc-fallback">
          <Icon name="file" size={28} />
          <span>PDF</span>
        </div>
      )}
      <div className="doc-scan-line" />
    </div>
  );
}

export default function App() {
  const [lang, setLang] = useState<'en' | 'ar'>('en');
  const [phase, setPhase] = useState<Phase>('empty');
  const [fileName, setFileName] = useState('');
  const [mimeType, setMimeType] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [result, setResult] = useState<ExtractResponse | null>(null);
  const [record, setRecord] = useState<IntakeRecord | null>(null);
  const [revealedSteps, setRevealedSteps] = useState<(ToolTraceStep & { atMs: number })[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [confirmedId, setConfirmedId] = useState<number | null>(null);
  const [confirmedAt, setConfirmedAt] = useState<Date | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const previewUrlRef = useRef<string | null>(null);
  const runStartRef = useRef(0);
  const t = copy[lang];
  const rtl = lang === 'ar';

  useEffect(() => {
    checkHealth().then(setOnline);
  }, []);

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  useEffect(() => {
    if (!running) return;
    const interval = window.setInterval(() => setElapsedMs(Date.now() - runStartRef.current), 83);
    return () => window.clearInterval(interval);
  }, [running]);

  function validateFile(name: string): boolean {
    if (!/\.(pdf|png|jpe?g)$/i.test(name)) {
      setError(t.uploadError);
      return false;
    }
    return true;
  }

  async function startRun(file: File) {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const url = URL.createObjectURL(file);
    previewUrlRef.current = url;
    setPreviewUrl(url);
    setFileName(file.name);
    setMimeType(file.type);
    setError('');
    setResult(null);
    setRecord(null);
    setConfirmedId(null);
    setRevealedSteps([]);
    setPhase('trace');
    setRunning(true);
    runStartRef.current = Date.now();
    setElapsedMs(0);

    try {
      const res = await extractTicket(file, lang);
      // The backend resolves the whole trace at once; reveal it step by step
      // so the run trace is still legible instead of dumping it all instantly.
      for (const step of res.trace) {
        await new Promise((resolve) => window.setTimeout(resolve, 420));
        setRevealedSteps((prev) => [...prev, { ...step, atMs: Date.now() - runStartRef.current }]);
      }
      await new Promise((resolve) => window.setTimeout(resolve, 500));
      setResult(res);
      setRecord({ ...res.record, material_type: humanizeMaterial(res.record.material_type) });
      setPhase('review');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase('empty');
    } finally {
      setRunning(false);
    }
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file && validateFile(file.name)) startRun(file);
    event.target.value = '';
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file && validateFile(file.name)) startRun(file);
  }

  async function handleSample(name: 'clean' | 'messy') {
    const blob = await fetch(SAMPLE_URLS[name]).then((r) => r.blob());
    const file = new File([blob], `ticket_${name}.png`, { type: 'image/png' });
    await startRun(file);
  }

  function handleUploadKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  function reset() {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = null;
    setPreviewUrl(null);
    setFileName('');
    setMimeType('');
    setError('');
    setResult(null);
    setRecord(null);
    setConfirmedId(null);
    setPhase('empty');
  }

  const confidenceByField = useMemo(() => {
    const map: Partial<Record<FieldKey, number>> = {};
    result?.field_confidences.forEach((f) => { map[f.field as FieldKey] = Math.round(f.confidence * 100); });
    return map;
  }, [result]);

  const flagsByField = useMemo(() => {
    const map: Partial<Record<FieldKey, string[]>> = {};
    result?.validation_flags.forEach((f) => {
      const key = f.field as FieldKey;
      (map[key] ??= []).push(f.message);
    });
    return map;
  }, [result]);

  const flaggedCount = useMemo(() => {
    if (!result) return 0;
    const fields = new Set<string>();
    result.field_confidences.filter((f) => f.confidence < 0.75).forEach((f) => fields.add(f.field));
    result.validation_flags.forEach((f) => fields.add(f.field));
    return fields.size;
  }, [result]);

  const rulesPassed = Math.max(0, RULE_KEYS.length - (result?.validation_flags.length ?? 0));

  function updateField(key: FieldKey, value: string) {
    setRecord((prev) => prev && ({ ...prev, [key]: key === 'weight_kg' ? Number(value) : value }));
  }

  async function handleConfirm() {
    if (!record) return;
    setConfirming(true);
    setError('');
    try {
      const submission = { ...record, material_type: snakeMaterial(record.material_type) };
      const { record_id } = await confirmRecord(submission, result?.run_id ?? null, lang);
      setConfirmedId(record_id);
      setConfirmedAt(new Date());
      setPhase('confirmed');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirming(false);
    }
  }

  function stepLabel(step: ToolTraceStep): string {
    return STEP_LABELS[step.step]?.[lang] ?? step.step;
  }

  function formatClock(ms: number): string {
    const totalSeconds = ms / 1000;
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = (totalSeconds % 60).toFixed(2);
    return `${String(minutes).padStart(2, '0')}:${seconds.padStart(5, '0')}`;
  }

  return (
    <div className="app" dir={rtl ? 'rtl' : 'ltr'} lang={lang}>
      <header className="topbar">
        <button className="brand" onClick={reset} aria-label="Groundtruth home">
          <span className="brand-mark"><span>GT</span></span>
          <span className="brand-name">{t.brand}<small>{t.edition}</small></span>
        </button>
        <div className="topbar-meta">
          <div className={`agent-live ${online === false ? 'is-offline' : ''}`}>
            <i />{online === false ? t.offline : t.live}
          </div>
          <div className="lang-toggle" aria-label="Language">
            <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
            <button className={lang === 'ar' ? 'active' : ''} onClick={() => setLang('ar')}>ع</button>
          </div>
        </div>
      </header>

      <main className={`shell phase-${phase}`}>
        <aside className="rail">
          <div>
            <p className="micro">{t.eyebrow}</p>
            <div className="rail-index">01<span>/01</span></div>
          </div>
          <div className="rail-status">
            <span>{t.queue}</span>
            <strong><i />{phase === 'empty' ? t.queueValue : fileName}</strong>
          </div>
          <p className="rail-footer">{t.footer}</p>
        </aside>

        <section className="workspace" aria-live="polite">
          {phase === 'empty' && (
            <div className="empty-view view-enter">
              <div className="hero-copy">
                <p className="eyebrow"><span>01</span>{t.start}</p>
                <h1>{t.headlineA}<br /><em>{t.headlineB}</em></h1>
                <p className="intro">{t.intro}</p>
              </div>
              <div className="intake-grid">
                <div>
                  <div className="dropzone" onDragOver={(e) => e.preventDefault()} onDrop={handleDrop} onClick={() => inputRef.current?.click()} onKeyDown={handleUploadKey} role="button" tabIndex={0}>
                    <input ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={handleFile} hidden />
                    <span className="corner c1" /><span className="corner c2" /><span className="corner c3" /><span className="corner c4" />
                    <div className="upload-icon"><Icon name="upload" size={25} /></div>
                    <h2>{t.dropTitle}</h2>
                    <p>{t.dropSub}</p>
                    <button className="primary-mini" type="button">{t.choose}<Icon name="arrow" /></button>
                  </div>
                  {error && <p className="form-error">{error}</p>}
                  <div className="sample-zone">
                    <span>{t.samples}</span>
                    <div className="sample-buttons">
                      <button onClick={() => handleSample('clean')}><Icon name="file" /><b>{t.sampleA}</b><small>{t.sampleTag}</small></button>
                      <button onClick={() => handleSample('messy')}><Icon name="file" /><b>{t.sampleB}</b><small>{t.sampleTag}</small></button>
                    </div>
                  </div>
                </div>
                <aside className="checks-card">
                  <div className="checks-head"><Icon name="shield" /><span>{t.checks}</span></div>
                  <ol>{t.checksList.map((item, index) => <li key={item}><span>0{index + 1}</span>{item}</li>)}</ol>
                  <p><Icon name="spark" />{t.audit}</p>
                </aside>
              </div>
            </div>
          )}

          {phase === 'trace' && (
            <div className="trace-view view-enter">
              <div className="section-head">
                <div><p className="eyebrow"><span>02</span>{t.running}</p><h1>{t.traceTitle}</h1><p>{t.traceSub}</p></div>
                <div className="run-clock"><i /><span>{t.runLabel}</span><b>{formatClock(elapsedMs)}</b></div>
              </div>
              <div className="process-grid">
                <div className="document-panel panel">
                  <div className="panel-label"><span>{t.preview}</span><b>{fileName}</b></div>
                  <DocumentView previewUrl={previewUrl} mimeType={mimeType} scanning />
                  <div className="document-meta"><span><i />{t.detected(revealedSteps.length)}</span><strong>{fileName}</strong></div>
                </div>
                <div className="trace-panel panel">
                  <div className="trace-top"><span>{t.liveTrace}</span><i /></div>
                  <ol className="trace-list">
                    {revealedSteps.map((step, i) => {
                      const isLast = i === revealedSteps.length - 1;
                      const cls = isLast ? 'current' : step.status === 'ok' ? 'done' : 'flagged';
                      return (
                        <li key={i} className={cls}>
                          <span className="step-node">{isLast ? (i + 1) : <Icon name="check" size={11} />}</span>
                          <div><strong>{stepLabel(step)}</strong><small>{step.detail}</small></div>
                          <time>{(step.atMs / 1000).toFixed(1)}s</time>
                        </li>
                      );
                    })}
                    {revealedSteps.length === 0 && (
                      <li className="current"><span className="step-node">…</span><div><strong>{t.running}</strong><small>{t.traceSub}</small></div><time>···</time></li>
                    )}
                  </ol>
                  <div className="trace-console">
                    <span>agent</span>
                    <code>{revealedSteps.length === 0 ? 'extract(ticket) → structured_record' : revealedSteps[revealedSteps.length - 1].step === 'result' ? 'return(record) → ready' : revealedSteps[revealedSteps.length - 1].step.startsWith('provider') ? 'extract(ticket) → structured_record' : 'validate(record) → checking rules'}</code>
                  </div>
                </div>
              </div>
            </div>
          )}

          {(phase === 'review' || phase === 'confirmed') && result && record && (
            <div className={`${phase === 'confirmed' ? 'confirmed-view' : 'review-view'} view-enter`}>
              {phase === 'review' && (
                <>
                  <div className="section-head review-heading">
                    <div>
                      <p className="eyebrow"><span>03</span>{t.reviewEyebrow}</p>
                      <h1>{flaggedCount > 0 ? t.reviewTitleFlagged(flaggedCount) : t.reviewTitleClean}</h1>
                      <p>{flaggedCount > 0 ? t.reviewSubFlagged : t.reviewSubClean}</p>
                    </div>
                    <div className={`review-status ${flaggedCount === 0 ? 'is-clean' : ''}`}>
                      <span><i />{flaggedCount > 0 ? t.statusReview : t.statusClean}</span>
                      <small><Icon name="check" size={13} />{t.passed(rulesPassed, RULE_KEYS.length)}</small>
                    </div>
                  </div>
                  {error && <div className="error-banner"><Icon name="shield" size={14} /><span><strong>{t.errorTitle}: </strong>{error}</span></div>}
                  <div className="review-grid">
                    <div className="review-source panel">
                      <div className="panel-label"><span>{t.preview}</span><b>{fileName}</b></div>
                      <DocumentView previewUrl={previewUrl} mimeType={mimeType} scanning={false} />
                      <div className="document-meta"><span><i />{t.via} {result.model}</span><strong>{fileName}</strong></div>
                    </div>
                    <div className="record-panel panel">
                      <div className="record-bar"><span>{t.structuredRecord}</span><code>run #{result.run_id ?? '—'}</code></div>
                      <div className="fields-grid">
                        {FIELD_KEYS.map((key) => {
                          const conf = confidenceByField[key];
                          const low = conf !== undefined && conf < 75;
                          const messages = flagsByField[key];
                          return (
                            <label key={key} className={`field ${low || messages ? 'field-low' : ''}`}>
                              <span className="field-label">{t.labels[key]}{(low || messages) && <em>{t.low}</em>}</span>
                              <span className="input-wrap">
                                <input value={String(record[key] ?? '')} onChange={(e) => updateField(key, e.target.value)} list={key === 'material_type' ? 'material-options' : undefined} />
                                {key === 'weight_kg' && <b className="unit">{t.kg}</b>}
                              </span>
                              {conf !== undefined && (
                                <span className="confidence-row"><i><b style={{ width: `${conf}%` }} /></i><small>{conf}% {t.confidence}</small></span>
                              )}
                              {(low || messages) && <span className="field-hint">↳ {messages?.[0] ?? t.editHint}</span>}
                            </label>
                          );
                        })}
                        <datalist id="material-options">
                          {MATERIAL_OPTIONS.map((opt) => <option key={opt} value={humanizeMaterial(opt)} />)}
                        </datalist>
                      </div>
                      <div className="confirm-row">
                        <p><Icon name="shield" />{t.confirmNote}</p>
                        <button className="confirm-button" onClick={handleConfirm} disabled={confirming}>
                          <span>{t.confirm}</span><Icon name="arrow" />
                        </button>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {phase === 'confirmed' && confirmedId !== null && (
                <>
                  <div className="confirmed-graphic"><span className="orbit o1" /><span className="orbit o2" /><div><Icon name="check" size={24} /></div></div>
                  <p className="eyebrow"><span>04</span>{t.confirmedEyebrow}</p>
                  <h1>{t.confirmedTitle}</h1>
                  <p className="confirmed-intro">{t.confirmedSub}</p>
                  <div className="receipt">
                    <div className="receipt-head"><span>{t.record} GT-{confirmedId}</span><strong><i />{t.accepted}</strong></div>
                    <div className="receipt-primary">
                      <div><span>{t.labels.material_type}</span><b>{record.material_type}</b></div>
                      <div><span>{t.labels.weight_kg}</span><b>{record.weight_kg} {t.kg}</b></div>
                    </div>
                    <div className="receipt-meta">
                      <div><span>{t.reference}</span><b>#{confirmedId}</b></div>
                      <div><span>{t.timestamp}</span><b>{(confirmedAt ?? new Date()).toLocaleTimeString(lang === 'ar' ? 'ar' : 'en-GB', { hour: '2-digit', minute: '2-digit' })}</b></div>
                      <div><span>{t.by}</span><b>{t.operator}</b></div>
                      <div><span>{t.ledger}</span><b>{(confirmedAt ?? new Date()).toISOString().slice(0, 10)}</b></div>
                    </div>
                  </div>
                  <button className="new-run" onClick={reset}><Icon name="rotate" />{t.newRun}</button>
                </>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
