import React, { useState } from 'react';
import { Box, Text } from 'ink';
import TextInput from 'ink-text-input';

interface UserInputProps {
  onSubmit: (text: string) => void;
}

export const UserInput: React.FC<UserInputProps> = ({ onSubmit }) => {
  const [value, setValue] = useState('');

  const handleSubmit = (text: string) => {
    if (text.trim()) {
      onSubmit(text);
      setValue('');
    }
  };

  return (
    <Box marginY={1}>
      <Box marginRight={1}>
        <Text color="cyanBright">❯</Text>
      </Box>
      <TextInput
        value={value}
        onChange={setValue}
        onSubmit={handleSubmit}
        placeholder="Type a message..."
      />
    </Box>
  );
};
