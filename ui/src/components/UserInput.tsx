import React, { useCallback, useRef, useState } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';

interface UserInputProps {
  onSubmit: (text: string) => void;
}

const BRACKETED_PASTE_START = '\u001b[200~';
const BRACKETED_PASTE_END = '\u001b[201~';
const CTRL_V_CHAR = '\u0016';

const normalizePromptText = (text: string): string => {
  const withoutPasteMarkers = text
    .replaceAll(BRACKETED_PASTE_START, '')
    .replaceAll(BRACKETED_PASTE_END, '');

  const flattenedLines = withoutPasteMarkers
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\n+/g, ' ')
    .replace(/\t/g, ' ');

  return flattenedLines.replace(/[ ]{2,}/g, ' ');
};

export const UserInput: React.FC<UserInputProps> = ({ onSubmit }) => {
  const [value, setValue] = useState('');
  const isPastingRef = useRef(false);

  const pasteFromClipboard = useCallback(async () => {
    if (isPastingRef.current) return;
    isPastingRef.current = true;

    try {
      const { default: clipboardy } = await import('clipboardy');
      const clipboardText = await clipboardy.read();
      if (!clipboardText) return;

      const normalized = normalizePromptText(clipboardText);
      setValue((prev) => normalizePromptText(`${prev}${normalized}`));
    } catch {
      // Ignore clipboard read failures to avoid breaking the input experience.
    } finally {
      isPastingRef.current = false;
    }
  }, []);

  useInput((input, key) => {
    if ((key.ctrl || key.meta) && (input === 'v' || input === 'V')) {
      void pasteFromClipboard();
    }
  });

  const handleChange = useCallback((nextValue: string) => {
    if (nextValue.includes(CTRL_V_CHAR)) {
      const withoutControlChar = nextValue.replaceAll(CTRL_V_CHAR, '');
      setValue(normalizePromptText(withoutControlChar));
      void pasteFromClipboard();
      return;
    }

    setValue(normalizePromptText(nextValue));
  }, [pasteFromClipboard]);

  const handleSubmit = useCallback((text: string) => {
    const normalized = normalizePromptText(text).trim();
    if (normalized) {
      onSubmit(normalized);
      setValue('');
    }
  }, [onSubmit]);

  return (
    <Box marginY={1}>
      <Box marginRight={1}>
        <Text color="cyanBright">❯</Text>
      </Box>
      <TextInput
        value={value}
        onChange={handleChange}
        onSubmit={handleSubmit}
        placeholder="Type a message..."
      />
    </Box>
  );
};
