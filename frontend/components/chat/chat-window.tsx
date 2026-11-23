"use client";

// Page Chat : dialogue avec l'assistant SmartCampus (SA-36 / SA-37).
// Chaque message passe par POST /api/v1/assistant/chat/{session_id} :
// le backend ajoute l'historique de la session et cumule le profil.

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  AssistantError,
  INTENT_LABELS,
  type Language,
  type LLMHealth,
  type Profil,
  type Understanding,
  getLLMHealth,
  resetConversation,
  sendChatMessage,
} from "@/lib/assistant";

type ChatMessage =
  | { id: number; role: "user"; text: string; language: Language }
  | { id: number; role: "assistant"; understanding: Understanding; profil: Profil; historySent: number }
  | { id: number; role: "error"; text: string };

type NewMessage = ChatMessage extends infer M ? (M extends ChatMessage ? Omit<M, "id"> : never) : never;

const LANGUAGES: { value: Language; label: string }[] = [
  { value: "fr", label: "Français" },
  { value: "en", label: "English" },
  { value: "arabizi", label: "Arabizi (tounsi)" },
];

const EXEMPLES: { text: string; language: Language }[] = [
  { text: "Nheb orientation fi IA, budget 4000 dt", language: "arabizi" },
  { text: "Je cherche une licence en informatique, pas en ligne", language: "fr" },
  { text: "I want to register in computer science online", language: "en" },
];

function newSessionId(): string {
  return crypto.randomUUID();
}

function formatBudget(budget: number | null): string {
  return budget === null ? "non précisé" : `${budget.toLocaleString("fr-FR")} DT`;
}

function formatOnline(online: boolean | null): string {
  if (online === null) return "non précisé";
  return online ? "oui, en ligne" : "non, sur place";
}

function StatusBadge({ health }: { health: LLMHealth | null | undefined }) {
  if (health === undefined) {
    return <span className="text-xs text-muted-foreground">Vérification de l&apos;assistant…</span>;
  }
  if (!health?.reachable) {
    return (
      <span className="rounded-full bg-destructive/10 px-2.5 py-1 text-xs font-medium text-destructive">
        Assistant hors ligne
      </span>
    );
  }
  if (health.mock) {
    return (
      <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-900">
        Mode test (mock)
      </span>
    );
  }
  return (
    <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-900">
      {health.model ?? "LLM"} en ligne
    </span>
  );
}

// Réponses rédigées à partir de l'intention (règles fixes, pas de génération) :
// l'assistant n'invente aucune information sur les formations avant le RAG.
const INTENT_REPLIES: Record<Understanding["intent"], string> = {
  orientation: "Je vous aide à trouver une formation adaptée.",
  information: "Je note votre question.",
  registration: "Je peux vous accompagner pour la préinscription.",
  confirm: "C'est noté, merci pour votre confirmation.",
  reschedule: "D'accord, je transmets votre demande de report de rendez-vous.",
  cancel: "D'accord, je prends en compte votre demande d'annulation.",
  unclear: "Je n'ai pas bien compris votre demande. Pouvez-vous la reformuler ?",
};

const INTENTS_PROFIL = new Set<Understanding["intent"]>(["orientation", "information", "registration"]);

function questionSuivante(understanding: Understanding, profil: Profil): string | null {
  if (!INTENTS_PROFIL.has(understanding.intent)) return null;
  if (profil.budget_dt === null) return "Quel est votre budget annuel, en dinars ?";
  if (profil.online === null) return "Préférez-vous une formation en ligne ou sur place ?";
  return "Merci, j'ai les informations principales de votre profil.";
}

function Avatar({ label, className }: { label: string; className: string }) {
  return (
    <span
      aria-hidden
      className={`flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${className}`}
    >
      {label}
    </span>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-full bg-background px-2 py-0.5 text-xs ring-1 ring-foreground/10">
      <span className="text-muted-foreground">{label} : </span>
      {value}
    </span>
  );
}

function AssistantBubble({
  understanding,
  profil,
  historySent,
}: {
  understanding: Understanding;
  profil: Profil;
  historySent: number;
}) {
  const question = questionSuivante(understanding, profil);
  return (
    <div className="flex max-w-[85%] items-end gap-2">
      <Avatar label="SC" className="bg-sky-700 text-white" />
      <div className="rounded-2xl rounded-bl-sm bg-muted px-4 py-3 text-sm">
        <p>{INTENT_REPLIES[understanding.intent]}</p>
        {question && <p className="mt-1 font-medium">{question}</p>}
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Detail label="Intention" value={INTENT_LABELS[understanding.intent]} />
          <Detail label="Budget" value={formatBudget(understanding.budget_dt)} />
          <Detail label="En ligne" value={formatOnline(understanding.online)} />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {historySent > 0 ? `Contexte : ${historySent} message(s) précédent(s) envoyés au LLM` : "Premier message de la conversation"}
          {understanding.mock ? " · réponse factice (mode mock)" : ""}
        </p>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-end gap-2" aria-label="L'assistant analyse votre message">
      <Avatar label="SC" className="bg-sky-700 text-white" />
      <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-muted px-4 py-3">
        {[0, 150, 300].map((delai) => (
          <span
            key={delai}
            className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
            style={{ animationDelay: `${delai}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

function ProfilCard({ profil }: { profil: Profil | null }) {
  const connus = profil ? [profil.intent, profil.budget_dt, profil.online].filter((v) => v !== null).length : 0;
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Profil du candidat</CardTitle>
        <div className="mt-1 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-sky-700 transition-all" style={{ width: `${(connus / 3) * 100}%` }} />
          </div>
          <span className="text-xs text-muted-foreground">{connus} / 3</span>
        </div>
      </CardHeader>
      <CardContent>
        {profil ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Dernière demande</dt>
            <dd>{profil.intent ? INTENT_LABELS[profil.intent] : "—"}</dd>
            <dt className="text-muted-foreground">Budget</dt>
            <dd>{formatBudget(profil.budget_dt)}</dd>
            <dt className="text-muted-foreground">En ligne</dt>
            <dd>{formatOnline(profil.online)}</dd>
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">
            Le profil se remplit au fil de la conversation. Une information donnée une fois est conservée.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function ChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState<Language>("fr");
  const [loading, setLoading] = useState(false);
  const [profil, setProfil] = useState<Profil | null>(null);
  const [health, setHealth] = useState<LLMHealth | null | undefined>(undefined);
  const sessionId = useRef<string | null>(null);
  const nextId = useRef(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getLLMHealth().then(setHealth);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function push(message: NewMessage) {
    setMessages((current) => [...current, { ...message, id: nextId.current++ } as ChatMessage]);
  }

  async function send(text: string, lang: Language) {
    const message = text.trim();
    if (!message || loading) return;
    sessionId.current ??= newSessionId();
    push({ role: "user", text: message, language: lang });
    setInput("");
    setLoading(true);
    try {
      const reponse = await sendChatMessage(sessionId.current, message, lang);
      push({
        role: "assistant",
        understanding: reponse.understanding,
        profil: reponse.profil,
        historySent: reponse.history_sent,
      });
      setProfil(reponse.profil);
    } catch (error) {
      const texte =
        error instanceof AssistantError ? error.message : "Une erreur inattendue est survenue. Réessayez.";
      push({ role: "error", text: texte });
      if (error instanceof AssistantError && (error.status === 503 || error.status === 0)) {
        getLLMHealth().then(setHealth);
      }
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  async function nouvelleConversation() {
    if (sessionId.current) await resetConversation(sessionId.current);
    sessionId.current = null;
    setMessages([]);
    setProfil(null);
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-4 md:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-xl bg-sky-700 text-sm font-bold text-white">
            SC
          </span>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">SmartCampus AI · Assistant d&apos;orientation</h1>
            <p className="text-sm text-muted-foreground">
              IIT · ISB · ISA · 2i2s — posez votre question en français, en anglais ou en tounsi (Arabizi).
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge health={health} />
          <Button variant="outline" onClick={nouvelleConversation} disabled={loading}>
            Nouvelle conversation
          </Button>
        </div>
      </header>

      <div className="grid flex-1 gap-6 md:grid-cols-[1fr_280px]">
        <Card className="h-[600px]">
          <CardContent className="flex min-h-0 flex-1 flex-col gap-4">
            <div className="flex flex-1 flex-col gap-3 overflow-y-auto" aria-live="polite">
              {messages.length === 0 && (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
                  <p className="text-sm text-muted-foreground">Essayez un exemple :</p>
                  <div className="flex flex-col gap-2">
                    {EXEMPLES.map((exemple) => (
                      <Button
                        key={exemple.text}
                        variant="secondary"
                        onClick={() => {
                          setLanguage(exemple.language);
                          send(exemple.text, exemple.language);
                        }}
                      >
                        {exemple.text}
                      </Button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message) => {
                if (message.role === "user") {
                  return (
                    <div key={message.id} className="flex items-end justify-end gap-2">
                      <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-sky-700 px-4 py-2 text-sm text-white">
                        {message.text}
                      </p>
                      <Avatar label="Vous" className="bg-muted text-[10px] text-muted-foreground" />
                    </div>
                  );
                }
                if (message.role === "assistant") {
                  return (
                    <div key={message.id} className="flex justify-start">
                      <AssistantBubble
                        understanding={message.understanding}
                        profil={message.profil}
                        historySent={message.historySent}
                      />
                    </div>
                  );
                }
                return (
                  <div key={message.id} className="flex justify-start">
                    <p role="alert" className="max-w-[85%] rounded-2xl rounded-bl-sm bg-destructive/10 px-4 py-2 text-sm text-destructive">
                      {message.text}
                    </p>
                  </div>
                );
              })}

              {loading && <TypingIndicator />}
              <div ref={bottomRef} />
            </div>

            <form
              className="flex flex-wrap gap-2 border-t pt-4"
              onSubmit={(event) => {
                event.preventDefault();
                send(input, language);
              }}
            >
              <label className="sr-only" htmlFor="langue">
                Langue
              </label>
              <select
                id="langue"
                value={language}
                onChange={(event) => setLanguage(event.target.value as Language)}
                className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
              >
                {LANGUAGES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <Input
                ref={inputRef}
                autoFocus
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Écrivez votre message…"
                maxLength={3000}
                aria-label="Votre message"
                className="flex-1"
              />
              <Button type="submit" disabled={loading || !input.trim()} className="bg-sky-700 text-white hover:bg-sky-800">
                Envoyer
              </Button>
            </form>
          </CardContent>
        </Card>

        <aside className="flex flex-col gap-4">
          <ProfilCard profil={profil} />
          <p className="text-xs text-muted-foreground">
            L&apos;assistant comprend votre demande (intention, budget, préférence en ligne). Les réponses
            détaillées sur les formations arriveront avec le RAG.
          </p>
        </aside>
      </div>
    </main>
  );
}
