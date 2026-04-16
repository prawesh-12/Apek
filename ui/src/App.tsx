import React, { useState, useEffect, useRef, useCallback } from 'react';
import { render, Box, Text } from 'ink';
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

const App = () => {
  const [agentState, setAgentState] = useState<AgentState>('thinking');
  const [messages, setMessages] = useState<MessageEntry[]>([]);
  const processRef = useRef<ChildProcessWithoutNullStreams | null>(null);

  // State to handle multi-line tool block reading
  const isReadingToolRef = useRef(false);
  const currentToolNameRef = useRef('');
  const currentToolArgsRef = useRef<string[]>([]);
  const currentToolIdRef = useRef('');

  // Pending messages queue -> flushed in one batch per data chunk (one frame debounce)
  // to avoid per line re-renders which cause scroll jumps and flicker.
  const pendingMessagesRef = useRef<MessageEntry[]>([]);
  const pendingStateRef = useRef<AgentState | null>(null);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current) return; // already scheduled
    flushTimerRef.current = setTimeout(() => {
      flushTimerRef.current = null;
      const pending = pendingMessagesRef.current;
      const nextState = pendingStateRef.current;
      pendingMessagesRef.current = [];
      pendingStateRef.current = null;

      if (pending.length > 0) {
        setMessages((prev) => {
          let next = [...prev];
          for (const msg of pending) {
            if (msg._op === 'append') {
              next = [...next, msg];
            } else if (msg._op === 'updateLastTool') {
              for (let i = next.length - 1; i >= 0; i--) {
                if (next[i].kind === 'tool') {
                  const tool = { ...(next[i] as ToolBlockEntry) };
                  tool.resultString = msg.resultString;
                  tool.isError = msg.isError;
                  next[i] = tool;
                  break;
                }
              }
            }
          }
          return next;
        });
      }
      if (nextState) setAgentState(nextState);
    }, 16); // one frame -> batch everything from the same data chunk
  }, []);

  const queueAppend = useCallback((msg: MessageEntry) => {
    pendingMessagesRef.current.push({ ...msg, _op: 'append' });
    scheduleFlush();
  }, [scheduleFlush]);

  const queueUpdateLastTool = useCallback((resultString: string, isError: boolean) => {
    pendingMessagesRef.current.push({ _op: 'updateLastTool', resultString, isError } as any);
    scheduleFlush();
  }, [scheduleFlush]);

  const queueState = useCallback((s: AgentState) => {
    pendingStateRef.current = s;
    scheduleFlush();
  }, [scheduleFlush]);

  useEffect(() => {
    // Spawn python agent unbuffered
    processRef.current = spawn('python3', ['-u', '../agent.py'], {
      stdio: ['pipe', 'pipe', 'pipe']
    });

    let buffer = '';

    const handleData = (data: Buffer) => {
      const text = data.toString('utf8');
      buffer += text;
      
      let newlineIdx;
      while ((newlineIdx = buffer.indexOf('\n')) !== -1) {
        const rawLine = buffer.slice(0, newlineIdx);
        buffer = buffer.slice(newlineIdx + 1);
        processLine(rawLine);
      }
      
      // If the buffer ends with "You:: " without a newline, input() doesn't send newline.
      const cleanBuffer = stripAnsi(buffer).trim();
      if (cleanBuffer === 'You::' || cleanBuffer === 'You:') {
        setAgentState('waiting_input');
        buffer = ''; // clear it so we don't process it infinitely
      }
    };

    if (processRef.current.stdout) {
      processRef.current.stdout.on('data', handleData);
    }
    
    // Also capture stderr
    if (processRef.current.stderr) {
      processRef.current.stderr.on('data', handleData);
    }

    return () => {
      if (processRef.current) {
        processRef.current.kill();
      }
    };
  }, []);

  const processLine = (rawLine: string) => {
    const line = stripAnsi(rawLine).trimEnd();
    
    if (!line) return;

    // Detect Input Prompt in a printed line (sometimes it flushes with newline)
    if (line.includes('You::') || line.includes('You:')) {
      // It's just a prompt
      setAgentState('waiting_input');
      // If the line only contains the prompt, we don't process further
      if (line.trim() === 'You::' || line.trim() === 'You:') {
        return;
      }
    }

    // Is it reading a multi-line tool block?
    if (isReadingToolRef.current) {
      queueState('tool_running');
      if (line.includes('└─')) {
        // End of block
        isReadingToolRef.current = false;
        const argsStr = currentToolArgsRef.current.join('\n');
        
        const newTool: ToolBlockEntry = {
          id: currentToolIdRef.current,
          kind: 'tool',
          toolName: currentToolNameRef.current,
          argsString: argsStr,
        };
        
        queueAppend(newTool);
        currentToolArgsRef.current = [];
        return;
      } else if (line.startsWith('│')) {
        // Collect args line
        const content = line.substring(1).trim(); // remove '│' prefix
        currentToolArgsRef.current.push(content);
        return;
      }
    }

    // 1. TOOL EXECUTION BLOCK
    if (line.includes('┌── Tool Execution:')) {
      isReadingToolRef.current = true;
      currentToolNameRef.current = line.split('Tool Execution:')[1].trim();
      currentToolIdRef.current = Date.now().toString() + Math.random().toString();
      currentToolArgsRef.current = [];
      queueState('tool_running');
      return;
    }

    // 2. TOOL RESULT
    if (line.includes('Tool Result:')) {
      const resultText = line.split('Tool Result:')[1].trim();
      const isError = resultText.includes('"error"');
      queueUpdateLastTool(resultText, isError);
      queueState('thinking');
      return;
    }

    // 3. AGENT RESPONSE
    if (line.startsWith('Apek:') || line.startsWith('Assistant:')) {
      const idx = line.indexOf(':');
      let text = line.substring(idx + 1).trim();
      if (text.startsWith(':')) {
         text = text.substring(1).trim();
      }
      queueAppend({ id: Date.now().toString() + Math.random().toString(), kind: 'agent', text });
      queueState('waiting_input');
      return;
    }

    // 4. STATUS MESSAGES
    if (line.startsWith('Status:')) {
      let text = line.substring('Status:'.length).trim();
      if (text.startsWith(':')) text = text.substring(1).trim();
      queueAppend({ id: Date.now().toString() + Math.random().toString(), kind: 'status', text });
      return;
    }
  };

  const handleSubmit = (text: string) => {
    setMessages((prev) => [
      ...prev,
      { id: Date.now().toString() + Math.random().toString(), kind: 'user', text },
    ]);
    
    setAgentState('thinking');
    
    if (processRef.current && processRef.current.stdin) {
      processRef.current.stdin.write(text + '\n');
    }
  };

  return (
    <Box flexDirection="column" width="100%">
      <AgentBanner />
      
      <Box flexDirection="column" marginTop={1}>
        {messages.map((m) => {
          if (m.kind === 'user') return <UserMessage key={m.id} text={m.text} />;
          if (m.kind === 'agent') return <AgentMessage key={m.id} text={m.text} />;
          if (m.kind === 'tool') return <ToolBlock key={m.id} data={m} />;
          if (m.kind === 'status') return <StatusMessage key={m.id} text={m.text} />;
          return null;
        })}
      </Box>

      {agentState === 'thinking' || agentState === 'tool_running' ? (
        <ThinkingSpinner />
      ) : (
        <UserInput onSubmit={handleSubmit} />
      )}
    </Box>
  );
};

// @ts-ignore
const webapp = render(<App />);

export default webapp;
