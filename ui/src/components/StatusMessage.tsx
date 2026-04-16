import React from 'react';
import { Box, Text } from 'ink';

interface StatusMessageProps {
  text: string;
}

const StatusMessageComponent: React.FC<StatusMessageProps> = ({ text }) => {
  return (
    <Box marginY={1}>
      <Text color="yellow">▲ </Text>
      <Text dimColor italic>{text}</Text>
    </Box>
  );
};

export const StatusMessage = React.memo(StatusMessageComponent);
