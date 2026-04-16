export type MessageKind = 
  | 'user'
  | 'agent'
  | 'tool'
  | 'status';

export interface UserMessageEntry {
  id: string;
  kind: 'user';
  text: string;
  _op?: 'append';
}

export interface AgentMessageEntry {
  id: string;
  kind: 'agent';
  text: string;
  _op?: 'append';
}

export interface ToolBlockEntry {
  id: string;
  kind: 'tool';
  toolName: string;
  argsString: string;
  resultString?: string;
  isError?: boolean;
  _op?: 'append' | 'updateLastTool';
}

export interface StatusMessageEntry {
  id: string;
  kind: 'status';
  text: string;
  _op?: 'append';
}

export type MessageEntry = 
  | UserMessageEntry 
  | AgentMessageEntry 
  | ToolBlockEntry 
  | StatusMessageEntry;

export type AgentState = 'waiting_input' | 'thinking' | 'tool_running';
