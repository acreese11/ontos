import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Send, Loader2, Sparkles, X, MessageSquare, Plus, Trash2, Check, CircleDot } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useToast } from '@/hooks/use-toast';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import LLMConsentDialog, { hasLLMConsent } from '@/components/common/llm-consent-dialog';
import { fetchLLMStatus, fetchSessions, sendMessage, deleteSession, streamContractDraft } from '@/components/search/llm-search-api';
import { useCopilotStore, PANEL_MIN_WIDTH, type CopilotPageContext } from '@/stores/copilot-store';
import { useCopilotQuestions } from '@/hooks/use-copilot-questions';
import type { LLMConfig } from '@/types/llm';
import type { ChatMessage, ContractDraftStage, LLMSearchStatus, SessionSummary } from '@/types/llm-search';

const WELCOME_DISMISSED_KEY = 'copilot-welcome-dismissed';

// "Draft a data contract for cat.sch.tbl" — the FQN must immediately follow
// "contract [for]" so we only divert to the streaming generator on a confident
// match; anything else (e.g. "create a contract spec — does a.b.c comply?")
// falls through to the normal agent chat. Identifier parts match the backend
// _IDENT_RE (leading non-digit) so the divert and the server agree.
const CONTRACT_DRAFT_INTENT =
  /\b(?:draft|generate|create|author)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:draft\s+)?(?:data\s+)?contract\s+(?:for\s+)?[`"']?([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b/i;

const STAGE_LABELS: Record<string, string> = {
  inspect_columns: 'Inspecting columns',
  sample_rows: 'Sampling rows',
  column_stats: 'Computing column stats',
  llm_call: 'Drafting with AI',
  parse_validate: 'Validating contract',
};

function upsertStage(stages: ContractDraftStage[], e: ContractDraftStage): ContractDraftStage[] {
  const idx = stages.findIndex((s) => s.step === e.step);
  if (idx === -1) return [...stages, e];
  const next = [...stages];
  next[idx] = { ...next[idx], ...e };
  return next;
}

function ContractStageChecklist({ stages, streaming }: { stages: ContractDraftStage[]; streaming?: boolean }) {
  if (!stages.length) return null;
  return (
    <ul className="mb-2 space-y-1">
      {stages.map((s) => {
        const done = s.status === 'done';
        return (
          <li key={s.step} className="flex items-center gap-2 text-xs">
            {done ? (
              <Check className="w-3 h-3 text-emerald-500 shrink-0" />
            ) : streaming ? (
              <Loader2 className="w-3 h-3 animate-spin text-violet-500 shrink-0" />
            ) : (
              <CircleDot className="w-3 h-3 text-muted-foreground shrink-0" />
            )}
            <span className={done ? 'text-muted-foreground' : 'font-medium'}>
              {STAGE_LABELS[s.step] ?? s.step}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function buildContextPrefix(ctx: CopilotPageContext): string {
  let prefix = `[Context: User is on the "${ctx.pageName}" page at ${ctx.pageUrl}`;
  if (ctx.selectedEntity) {
    prefix += `, viewing ${ctx.selectedEntity.type} "${ctx.selectedEntity.name}" (id: ${ctx.selectedEntity.id})`;
  }
  prefix += '. Consider this context when answering.]';
  return prefix;
}

function CopilotMessage({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
      {!isUser && (
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shrink-0">
          <Sparkles className="w-3 h-3 text-white" />
        </div>
      )}
      <div className={`
        max-w-[85%] rounded-lg px-3 py-2 text-sm
        ${isUser
          ? 'bg-sky-100 dark:bg-sky-900/50 text-sky-900 dark:text-sky-100'
          : 'bg-muted'
        }
      `}>
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
            {message.stages && (
              <ContractStageChecklist stages={message.stages} streaming={message.streaming} />
            )}
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ children }) => (
                  <div className="overflow-x-auto my-1">
                    <table className="min-w-full border-collapse text-xs">{children}</table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-border bg-muted px-2 py-1 text-left font-medium">{children}</th>
                ),
                td: ({ children }) => (
                  <td className="border border-border px-2 py-1">{children}</td>
                ),
                code: ({ className, children, ...props }) => {
                  const isInline = !className;
                  return isInline ? (
                    <code className="bg-muted-foreground/20 px-1 py-0.5 rounded text-xs" {...props}>{children}</code>
                  ) : (
                    <code className={`${className} block bg-zinc-900 text-zinc-100 p-2 rounded-md overflow-x-auto text-xs`} {...props}>{children}</code>
                  );
                },
              }}
            >
              {message.content || ''}
            </ReactMarkdown>
            {message.contractUrl && (
              <a
                href={message.contractUrl}
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-violet-600 dark:text-violet-400 hover:underline no-underline"
              >
                Open draft in contract editor →
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CopilotPanel() {
  const { t } = useTranslation(['search', 'common']);
  const isOpen = useCopilotStore((s) => s.isOpen);
  const pageContext = useCopilotStore((s) => s.pageContext);
  const panelWidth = useCopilotStore((s) => s.panelWidth);
  const { closePanel, setPanelWidth, setResizing } = useCopilotStore((s) => s.actions);
  const questionGroups = useCopilotQuestions();

  const [status, setStatus] = useState<LLMSearchStatus | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showConsentDialog, setShowConsentDialog] = useState(false);
  const [isWelcomeDismissed, setIsWelcomeDismissed] = useState(
    () => localStorage.getItem(WELCOME_DISMISSED_KEY) === 'true',
  );

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  // Drag-resizable panel width lives in the store so the main layout can reserve
  // matching space (otherwise the fixed panel overlays + cuts off page content).
  const startResize = (e: React.MouseEvent) => {
    e.preventDefault();
    // Cap = smaller of "leave an 80px sliver" and the panel's CSS 95vw cap, so
    // the layout's reserved margin matches the panel's actual width (no gap).
    const maxW = Math.max(480, Math.min(window.innerWidth - 80, Math.round(window.innerWidth * 0.95)));
    setResizing(true);
    const onMove = (ev: MouseEvent) => {
      setPanelWidth(Math.min(Math.max(window.innerWidth - ev.clientX, PANEL_MIN_WIDTH), maxW));
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      setResizing(false);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.body.style.userSelect = 'none';
  };

  const llmConfig: LLMConfig = {
    enabled: status?.enabled ?? false,
    endpoint: status?.endpoint ?? null,
    system_prompt: null,
    disclaimer_text: status?.disclaimer ?? '',
  };

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);

  useEffect(() => {
    if (!isOpen) return;
    async function load() {
      try {
        const [statusData, sessionsData] = await Promise.all([
          fetchLLMStatus(),
          fetchSessions(),
        ]);
        setStatus(statusData);
        setSessions(sessionsData);
      } catch {
        // silently fail on panel open
      }
    }
    load();
  }, [isOpen]);

  const dismissWelcome = () => {
    setIsWelcomeDismissed(true);
    localStorage.setItem(WELCOME_DISMISSED_KEY, 'true');
  };

  const handleStreamContract = async (
    catalog: string,
    schema: string,
    table: string,
    rawText: string,
  ) => {
    const userMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: rawText,
      timestamp: new Date().toISOString(),
    };
    const asstId = `stream-${Date.now()}`;
    const asstMessage: ChatMessage = {
      id: asstId,
      role: 'assistant',
      content: '',
      streaming: true,
      stages: [],
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage, asstMessage]);
    setInput('');
    setIsLoading(true);

    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((prev) => prev.map((m) => (m.id === asstId ? fn(m) : m)));

    // Batch token renders: re-running ReactMarkdown over the growing contract on
    // every delta is O(n²). Coalesce to ~1 render / 80ms; terminal handlers
    // cancel the pending flush and set final content.
    let draft = '';
    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    const flushDraft = () => {
      flushTimer = null;
      patch((m) => ({ ...m, content: '```json\n' + draft + '\n```' }));
    };
    const cancelFlush = () => {
      if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
    };
    try {
      await streamContractDraft(
        { catalog, schema, table, sessionId: currentSessionId },
        {
          // Adopt the copilot session the server recorded this draft turn into so
          // subsequent turns continue it (mirrors chat's response.session_id).
          onSession: (id) => setCurrentSessionId(id),
          onStage: (s) => patch((m) => ({ ...m, stages: upsertStage(m.stages ?? [], s as ContractDraftStage) })),
          onToken: (delta) => {
            draft += delta;
            if (!flushTimer) flushTimer = setTimeout(flushDraft, 80);
          },
          onResult: (r) => {
            cancelFlush();
            const c = r.contract as { name?: string; version?: string } | null;
            const header = c?.name
              ? `**Drafted \`${c.name}\`${c.version ? ` v${c.version}` : ''}** — review and refine below.\n\n`
              : '**Draft complete.**\n\n';
            const body = c ? '```json\n' + JSON.stringify(c, null, 2) + '\n```' : '';
            patch((m) => ({
              ...m,
              streaming: false,
              content: header + body,
              contractUrl: r.contract_id ? `/data-contracts/${r.contract_id}?ai-draft=true` : undefined,
            }));
          },
          onExists: (e) => { cancelFlush(); patch((m) => ({ ...m, streaming: false, content: e.message })); },
          onError: (msg) => {
            cancelFlush();
            patch((m) => ({ ...m, streaming: false, isError: true, content: `⚠️ ${msg}` }));
            toast({ title: t('common:toast.error'), description: msg, variant: 'destructive' });
          },
        },
      );
    } catch (err) {
      cancelFlush();
      const errorMessage = err instanceof Error ? err.message : t('search:copilot.messageSendFailed');
      patch((m) => ({ ...m, streaming: false, isError: true, content: `⚠️ ${errorMessage}` }));
      toast({ title: t('common:toast.error'), description: errorMessage, variant: 'destructive' });
    } finally {
      cancelFlush();
      setIsLoading(false);
      inputRef.current?.focus();
      // Refresh the history dropdown so the recorded draft session shows up
      // (the chat path does the same after sendMessage).
      try {
        setSessions(await fetchSessions());
      } catch {
        // non-fatal: history list just won't refresh
      }
    }
  };

  const handleSend = async () => {
    const messageContent = input.trim();
    if (!messageContent || isLoading) return;

    if (!hasLLMConsent(llmConfig)) {
      setShowConsentDialog(true);
      return;
    }

    // Confident "draft a contract for cat.sch.tbl" → live streaming generator;
    // everything else goes to the normal agent chat.
    const draftMatch = messageContent.match(CONTRACT_DRAFT_INTENT);
    if (draftMatch) {
      handleStreamContract(draftMatch[1], draftMatch[2], draftMatch[3], messageContent);
      return;
    }

    let contextualMessage = messageContent;
    if (pageContext) {
      contextualMessage = buildContextPrefix(pageContext) + '\n\n' + messageContent;
    }

    const userMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: messageContent,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await sendMessage(contextualMessage, currentSessionId);
      setCurrentSessionId(response.session_id);
      setMessages((prev) => [...prev, response.message]);
      const updatedSessions = await fetchSessions();
      setSessions(updatedSessions);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : t('search:copilot.messageSendFailed');
      toast({ title: t('common:toast.error'), description: errorMessage, variant: 'destructive' });
      setMessages((prev) => prev.filter((m) => m.id !== userMessage.id));
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSelectPrompt = (prompt: string) => {
    setInput(prompt);
    inputRef.current?.focus();
  };

  const handleConsentAccepted = () => {
    if (input.trim()) {
      setTimeout(() => handleSend(), 100);
    }
  };

  const handleSelectSession = async (sessionId: string) => {
    try {
      const response = await fetch(`/api/llm-search/sessions/${sessionId}`);
      if (!response.ok) throw new Error('Failed to load session');
      const session = await response.json();
      setCurrentSessionId(session.id);
      setMessages(session.messages.filter((m: ChatMessage) =>
        m.role === 'user' || (m.role === 'assistant' && m.content)
      ));
    } catch {
      toast({
        title: t('common:toast.error'),
        description: t('search:llm.messages.loadSessionFailed'),
        variant: 'destructive',
      });
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        setCurrentSessionId(undefined);
        setMessages([]);
      }
      toast({
        title: t('search:llm.messages.sessionDeleted'),
        description: t('search:llm.messages.sessionDeletedDesc'),
      });
    } catch {
      toast({
        title: t('common:toast.error'),
        description: t('search:llm.messages.deleteSessionFailed'),
        variant: 'destructive',
      });
    }
  };

  const handleNewSession = () => {
    setCurrentSessionId(undefined);
    setMessages([]);
    inputRef.current?.focus();
  };

  if (!isOpen) return null;

  return (
    <>
      <LLMConsentDialog
        open={showConsentDialog}
        onOpenChange={setShowConsentDialog}
        onAccept={handleConsentAccepted}
        llmConfig={llmConfig}
      />

      {/* Panel container — fixed right side, no overlay */}
      <div
        className="fixed inset-y-0 right-0 z-50 border-l bg-background shadow-lg flex flex-col animate-in slide-in-from-right duration-300"
        style={{ width: panelWidth, maxWidth: '95vw' }}
      >
        {/* Drag handle — resize the panel relative to the main window */}
        <div
          onMouseDown={startResize}
          className="absolute inset-y-0 left-0 w-1.5 -ml-0.5 cursor-col-resize z-10 group"
          title="Drag to resize"
        >
          <div className="h-full w-px mx-auto bg-border group-hover:bg-violet-400 group-hover:w-0.5 transition-colors" />
        </div>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <div>
              <h2 className="text-sm font-semibold leading-tight">{t('search:copilot.title')}</h2>
              <p className="text-xs text-muted-foreground">{t('search:copilot.subtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {/* History dropdown */}
            {sessions.length > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-7 w-7" title={t('search:llm.history')}>
                    <MessageSquare className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                  <DropdownMenuItem onClick={handleNewSession} className="gap-2">
                    <Plus className="w-4 h-4" />
                    {t('search:llm.newConversation')}
                  </DropdownMenuItem>
                  <Separator className="my-1" />
                  {sessions.map((session) => (
                    <DropdownMenuItem
                      key={session.id}
                      className={`flex justify-between items-center gap-2 ${
                        session.id === currentSessionId ? 'bg-accent' : ''
                      }`}
                      onClick={() => handleSelectSession(session.id)}
                    >
                      <span className="truncate flex-1">
                        {session.title || t('search:llm.untitled')}
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 opacity-60 hover:opacity-100"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteSession(session.id);
                        }}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={closePanel}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Context badge */}
        {pageContext?.selectedEntity && (
          <div className="px-4 py-2 border-b bg-muted/30 shrink-0">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{t('search:copilot.askingAbout')}</span>
              <Badge variant="outline" className="text-xs font-medium">
                {pageContext.selectedEntity.name}
              </Badge>
              <Badge variant="secondary" className="text-xs">
                {pageContext.selectedEntity.type}
              </Badge>
            </div>
          </div>
        )}

        {/* Messages / Welcome */}
        <ScrollArea className="flex-1 min-h-0">
          <div className="p-4">
            {messages.length === 0 ? (
              <div className="space-y-5">
                {/* Dismissable welcome card */}
                {!isWelcomeDismissed && (
                  <div className="rounded-lg border bg-muted/30 p-4 relative">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="absolute top-1 right-1 h-6 w-6 text-muted-foreground hover:text-foreground"
                      onClick={dismissWelcome}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                    <div className="flex items-start gap-2 pr-6">
                      <Sparkles className="w-4 h-4 text-violet-500 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-sm font-medium">{t('search:copilot.welcome')}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {t('search:copilot.welcomeDescription')}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Context- and role-aware prompts */}
                {questionGroups.map((group) => (
                  <div key={group.category}>
                    <h3 className="text-xs font-medium text-muted-foreground mb-2">
                      {group.label}
                    </h3>
                    <div className="space-y-1.5">
                      {group.questions.map((q) => (
                        <button
                          key={q.key}
                          className="w-full text-left text-sm px-3 py-2 rounded-md border bg-background hover:bg-accent transition-colors"
                          onClick={() => handleSelectPrompt(q.text)}
                        >
                          {q.text}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((message) => (
                  <CopilotMessage key={message.id} message={message} />
                ))}
                {isLoading && !messages.some((m) => m.streaming) && (
                  <div className="flex gap-2">
                    <div className="w-6 h-6 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shrink-0">
                      <Sparkles className="w-3 h-3 text-white" />
                    </div>
                    <div className="bg-muted rounded-lg px-3 py-2 flex items-center gap-2">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      <span className="text-xs text-muted-foreground">{t('search:llm.thinking')}</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </ScrollArea>

        <Separator />

        {/* Input */}
        <div className="p-3 shrink-0">
          <div className="flex gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('search:copilot.inputPlaceholder')}
              className="flex-1 h-9 rounded-md border border-input bg-background px-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
              disabled={isLoading}
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              size="icon"
              className="h-9 w-9 shrink-0"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
