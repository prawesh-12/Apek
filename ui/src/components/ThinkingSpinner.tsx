import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';

const FRAMES = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'];

/**
 * Spinner that uses its OWN local state,,,,,so its setInterval ticks
 * only re-render this tiny leaf component, NOT the parent App.
 * This prevents the ~80ms ink-spinner internal timer from triggering
 * a full terminal repaint (which caused scroll jump + flicker).
 */
export const ThinkingSpinner = () => {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setFrame((f) => (f + 1) % FRAMES.length);
    }, 120);
    return () => clearInterval(id);
  }, []);

  return (
    <Box marginY={1}>
      <Text color="magentaBright">{FRAMES[frame]}</Text>
      <Text dimColor italic> Apek is thinking...</Text>
    </Box>
  );
};
