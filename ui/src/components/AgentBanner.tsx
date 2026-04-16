import React, { useMemo } from 'react';
import { Box, Text } from 'ink';
import fs from 'fs';
import path from 'path';

export const AgentBanner = () => {
  const modelName = useMemo(() => {
    try {
      const envPath = path.resolve(process.cwd(), '../.env');
      const envContent = fs.readFileSync(envPath, 'utf8');
      const match = envContent.match(/OLLAMA_MODEL=(.*)/);
      if (match) return match[1].trim();
    } catch (e) {}
    return 'Unknown Model';
  }, []);

  const asciiArt = `
█████╗ ██████╗ ███████╗██╗  ██╗
██╔══██╗██╔══██╗██╔════╝██║ ██╔╝
███████║██████╔╝█████╗  █████╔╝ 
██╔══██║██╔═══╝ ██╔══╝  ██╔═██╗ 
██║  ██║██║     ███████╗██║  ██╗
╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝
`.trim();

  return (
    <Box flexDirection="column" marginBottom={1} padding={1} borderStyle="round" borderColor="magenta">
      <Text color="magentaBright" bold>
        {asciiArt}
      </Text>
      <Box marginTop={1} justifyContent="space-between" width="100%">
        <Text dimColor>Agentic Coding Assistant ({modelName})</Text>
        <Box>
          <Text color="greenBright">● </Text>
          <Text color="green">Running </Text>
          <Text dimColor>(python3 agent.py)</Text>
        </Box>
      </Box>
    </Box>
  );
};
