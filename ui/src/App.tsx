import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { render, Box, Static } from 'ink';
import { spawn, ChildProcessWithoutNullStreams } from 'child_process';

import {
  AgentState,
  MessageEntry,
  ToolBlockEntry
} from './types';

import { AgentBanner } from './components/AgentBanner';
import { UserMessage } from './components/UserMessage';
import { AgentMessage } from './components/AgentMessage';
import { ToolBlock } from './components/ToolBlock';
import { ThinkingSpinner } from './components/ThinkingSpinner';
import { StatusMessage } from './components/StatusMessage';
import { UserInput } from './components/UserInput';

const stripAnsi = (str: string) => str.replace(/\x1B\[[0-9;]*m/g, '');

type UiState = {
  agentState: AgentState;
  messages: MessageEntry[];
};

type PendingMessageOp = MessageEntry & { _op: 'append' };

type PendingToolBlock = {
  id: string;
  toolName: string;
  argsString: string;
};

type StaticFeedItem =
  | { id: 'banner'; kind: 'banner' }
  | { id: string; kind: 'message'; entry: MessageEntry };

const renderMessage = (message: MessageEntry) => {
  if (message.kind === 'user') return <UserMessage text={message.text} />;
  if (message.kind === 'agent') return <AgentMessage text={message.text} />;
  if (message.kind === 'tool') return <ToolBlock data={message} />;
  if (message.kind === 'status') return <StatusMessage text={message.text} />;
  return null;
};

const App = () => {
  const [uiState, setUiState] = useState<UiState>({
    agentState: 'thinking',
    messages: [],
  });
  const { agentState, messages } = uiState;

  const processRef = useRef<ChildProcessWithoutNullStreams | null>(null);
  const agentStateRef = useRef<AgentState>('thinking');
  const nextMessageIdRef = useRef(1);

  // State to handle multi-line tool block reading
  const isReadingToolRef = useRef(false);
  const currentToolNameRef = useRef('');
  const currentToolArgsRef = useRef<string[]>([]);
  const currentToolIdRef = useRef('');
  const pendingToolBlockRef = useRef<PendingToolBlock | null>(null);
  const staticBannerItemRef = useRef<StaticFeedItem>({ id: 'banner', kind: 'banner' });

  // Pending messages queue -> flushed in one batch per data chunk (one frame debounce)
  // to avoid per line re-renders which cause scroll jumps and flicker.
  const pendingMessagesRef = useRef<PendingMessageOp[]>([]);
  const pendingStateRef = useRef<AgentState | null>(null);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    agentStateRef.current = agentState;
  }, [agentState]);

  const createMessageId = useCallback(() => {
    const id = nextMessageIdRef.current;
    nextMessageIdRef.current += 1;
    return `msg_${id}`;
  }, []);

  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current) return;

    flushTimerRef.current = setTimeout(() => {
      flushTimerRef.current = null;

      const pendingOps = pendingMessagesRef.current;
      const queuedState = pendingStateRef.current;
      pendingMessagesRef.current = [];
      pendingStateRef.current = null;

      if (pendingOps.length === 0 && queuedState === null) return;

      setUiState((prev) => {
        let nextMessages = prev.messages;
        let messagesChanged = false;

        for (const op of pendingOps) {
          if (op._op === 'append') {
            if (!messagesChanged) {
              nextMessages = [...nextMessages];
              messagesChanged = true;
            }

            const { _op, ...message } = op;
            nextMessages.push(message as MessageEntry);
          }
        }

        const nextAgentState = queuedState ?? prev.agentState;
        const stateChanged = nextAgentState !== prev.agentState;

        if (!messagesChanged && !stateChanged) {
          return prev;
        }

        if (stateChanged) {
          agentStateRef.current = nextAgentState;
        }

        return {
          messages: messagesChanged ? nextMessages : prev.messages,
          agentState: nextAgentState,
        };
      });
    }, 16);
  }, []);

  const queueAppend = useCallback((msg: MessageEntry) => {
    pendingMessagesRef.current.push({ ...msg, _op: 'append' });
    scheduleFlush();
  }, [scheduleFlush]);

  const queueState = useCallback((nextState: AgentState) => {
    const effectiveState = pendingStateRef.current ?? agentStateRef.current;
    if (effectiveState === nextState) return;

    pendingStateRef.current = nextState;
    scheduleFlush();
  }, [scheduleFlush]);

  useEffect(() => {
    const preferredPython = process.env.PYTHON_BIN?.trim();
    const pythonExecutable =
      preferredPython && preferredPython.length > 0
        ? preferredPython
        : process.platform === 'win32'
          ? 'python'
          : 'python3';

    processRef.current = spawn(pythonExecutable, ['-u', '../agent.py'], {
      stdio: ['pipe', 'pipe', 'pipe']
    });

    processRef.current.on('error', (err: Error) => {
      queueAppend({
        id: createMessageId(),
        kind: 'status',
        text: `Failed to launch ${pythonExecutable}. Set PYTHON_BIN or ensure Python is on PATH. ${err.message}`,
      });
      queueState('waiting_input');
    });

    let buffer = '';

    const processLine = (rawLine: string) => {
      const line = stripAnsi(rawLine).trimEnd();
      if (!line) return;

      if (line.includes('You::') || line.includes('You:')) {
        queueState('waiting_input');
        if (line.trim() === 'You::' || line.trim() === 'You:') {
          return;
        }
      }

      if (isReadingToolRef.current) {
        queueState('tool_running');
        if (line.includes('└─')) {
          isReadingToolRef.current = false;
          const argsStr = currentToolArgsRef.current.join('\n');

          const newTool: PendingToolBlock = {
            id: currentToolIdRef.current,
            toolName: currentToolNameRef.current,
            argsString: argsStr,
          };

          pendingToolBlockRef.current = newTool;
          currentToolArgsRef.current = [];
          return;
        }

        if (line.startsWith('│')) {
          const content = line.substring(1).trim();
          currentToolArgsRef.current.push(content);
          return;
        }
      }

      if (line.includes('┌── Tool Execution:')) {
        if (pendingToolBlockRef.current) {
          queueAppend({
            id: pendingToolBlockRef.current.id,
            kind: 'tool',
            toolName: pendingToolBlockRef.current.toolName,
            argsString: pendingToolBlockRef.current.argsString,
            resultString: '{"error":"Tool finished without explicit Tool Result output"}',
            isError: true,
          });
          pendingToolBlockRef.current = null;
        }

        isReadingToolRef.current = true;
        currentToolNameRef.current = line.split('Tool Execution:')[1].trim();
        currentToolIdRef.current = createMessageId();
        currentToolArgsRef.current = [];
        queueState('tool_running');
        return;
      }

      if (line.includes('Tool Result:')) {
        const resultText = line.split('Tool Result:')[1].trim();
        const isError = resultText.includes('"error"');

        if (pendingToolBlockRef.current) {
          const finalizedTool: ToolBlockEntry = {
            id: pendingToolBlockRef.current.id,
            kind: 'tool',
            toolName: pendingToolBlockRef.current.toolName,
            argsString: pendingToolBlockRef.current.argsString,
            resultString: resultText,
            isError,
          };
          queueAppend(finalizedTool);
          pendingToolBlockRef.current = null;
        } else {
          queueAppend({
            id: createMessageId(),
            kind: 'status',
            text: `Tool result arrived without tool header: ${resultText}`,
          });
        }

        queueState('thinking');
        return;
      }

      if (line.startsWith('Apek:') || line.startsWith('Assistant:')) {
        const idx = line.indexOf(':');
        let text = line.substring(idx + 1).trim();
        if (text.startsWith(':')) {
          text = text.substring(1).trim();
        }
        queueAppend({ id: createMessageId(), kind: 'agent', text });
        queueState('waiting_input');
        return;
      }

      if (line.startsWith('Status:')) {
        let text = line.substring('Status:'.length).trim();
        if (text.startsWith(':')) text = text.substring(1).trim();
        queueAppend({ id: createMessageId(), kind: 'status', text });
      }
    };

    const handleData = (data: Buffer) => {
      const text = data
        .toString('utf8')
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n');
      buffer += text;

      let newlineIdx;
      while ((newlineIdx = buffer.indexOf('\n')) !== -1) {
        const rawLine = buffer.slice(0, newlineIdx);
        buffer = buffer.slice(newlineIdx + 1);
        processLine(rawLine);
      }

      const cleanBuffer = stripAnsi(buffer).trim();
      if (cleanBuffer === 'You::' || cleanBuffer === 'You:') {
        queueState('waiting_input');
        buffer = '';
      }
    };

    if (processRef.current.stdout) {
      processRef.current.stdout.on('data', handleData);
    }

    if (processRef.current.stderr) {
      processRef.current.stderr.on('data', handleData);
    }

    return () => {
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      if (processRef.current) {
        processRef.current.kill();
      }
    };
  }, [createMessageId, queueAppend, queueState]);

  const handleSubmit = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setUiState((prev) => {
      const nextAgentState: AgentState = 'thinking';
      agentStateRef.current = nextAgentState;

      return {
        agentState: nextAgentState,
        messages: [...prev.messages, { id: createMessageId(), kind: 'user', text: trimmed }],
      };
    });

    if (processRef.current && processRef.current.stdin) {
      processRef.current.stdin.write(trimmed + '\n');
    }
  }, [createMessageId]);

  const staticFeedItems = useMemo<StaticFeedItem[]>(() => {
    return [
      staticBannerItemRef.current,
      ...messages.map((entry) => ({
        id: entry.id,
        kind: 'message' as const,
        entry,
      })),
    ];
  }, [messages]);

  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="column">
        <Static items={staticFeedItems}>
          {(item) => (
            <Box key={item.id} flexDirection="column" width="100%">
              {item.kind === 'banner' ? <AgentBanner /> : renderMessage(item.entry)}
            </Box>
          )}
        </Static>
      </Box>

      <Box minHeight={4}>
        {agentState === 'thinking' || agentState === 'tool_running' ? (
          <ThinkingSpinner />
        ) : (
          <UserInput onSubmit={handleSubmit} />
        )}
      </Box>
    </Box>
  );
};

// @ts-ignore
const webapp = render(<App />);

export default webapp;
