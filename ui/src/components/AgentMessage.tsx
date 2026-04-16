import React from 'react';
import { Box, Text } from 'ink';

interface AgentMessageProps {
  text: string;
}

export const AgentMessage: React.FC<AgentMessageProps> = ({ text }) => {
  const cleanedText = text.replace(/[\u{1F000}-\u{1FFFF}\u{2600}-\u{27FF}]/gu, '').trim();

  return (
    <Box flexDirection="column" marginY={1} paddingLeft={1} borderStyle="single" borderLeft borderRight={false} borderTop={false} borderBottom={false} borderColor="magenta">
      <Text color="magentaBright" bold>◈ Apek</Text>
      <Box marginTop={1}>
        <Text>{cleanedText}</Text>
      </Box>
    </Box>
  );
};
