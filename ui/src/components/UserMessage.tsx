import React from 'react';
import { Box, Text } from 'ink';

interface UserMessageProps {
  text: string;
}

export const UserMessage: React.FC<UserMessageProps> = ({ text }) => {
  return (
    <Box marginY={1}>
      <Text color="cyanBright">❯ </Text>
      <Text color="white" bold>{text}</Text>
    </Box>
  );
};
