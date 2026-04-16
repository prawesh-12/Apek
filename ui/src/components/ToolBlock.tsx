import React from 'react';
import { Box, Text } from 'ink';
import { ToolBlockEntry } from '../types';

interface ToolBlockProps {
  data: ToolBlockEntry;
}

const ToolBlockComponent: React.FC<ToolBlockProps> = ({ data }) => {
  // Parse args string for preview mapping
  let argsObj: any = {};
  try {
    argsObj = JSON.parse(data.argsString);
  } catch (e) { }

  let previewNode: React.ReactNode = null;

  if (data.toolName === 'edit_file' && typeof argsObj.new_str === 'string') {
    const lines = argsObj.new_str.split('\n');
    const firstSix = lines.slice(0, 6);
    const hasMore = lines.length > 6;
    const remaining = lines.length - 6;

    previewNode = (
      <Box flexDirection="column" marginTop={1}>
        <Text color="cyanBright"> ◆ Preview</Text>
        <Box flexDirection="column" paddingLeft={1} borderStyle="single" borderRight={false} borderTop={false} borderBottom={false} borderColor="gray">
          {firstSix.map((line: string, idx: number) => (
            <Text dimColor key={idx}>{String(idx + 1).padStart(3, ' ')} │ {line}</Text>
          ))}
          {hasMore && <Text dimColor>  ··· (+{remaining} more lines)</Text>}
        </Box>
      </Box>
    );
  } else if (data.toolName === 'execute_command' && typeof argsObj.command === 'string') {
    previewNode = (
      <Box marginTop={1} flexDirection="column">
        <Text color="cyanBright"> ◆ Preview</Text>
        <Box paddingLeft={2}>
          <Text><Text color="greenBright">$ </Text><Text color="whiteBright" bold>{argsObj.command}</Text></Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginY={1} marginLeft={2}>
      <Box>
        <Text backgroundColor="yellow" color="black" bold> ◎ TOOL </Text>
        <Text color="yellowBright" bold> {data.toolName}</Text>
      </Box>
      <Box paddingLeft={2} marginTop={1}>
        <Text dimColor>{data.argsString}</Text>
      </Box>

      {previewNode}

      {data.resultString && (() => {
        let isErr = data.isError;
        let displayResult = data.resultString;

        try {
          const resObj = JSON.parse(data.resultString);
          if (resObj.error) {
            displayResult = resObj.error;
            isErr = true;
          } else if (data.toolName === 'execute_command') {
            const code = resObj.returncode;
            if (code !== undefined && code !== 0) {
              isErr = true;
              displayResult = `exit ${code}${resObj.stderr ? `  │  stderr: "${resObj.stderr}"` : ''}`;
            } else if (code === 0) {
              isErr = false;
              displayResult = `exit 0${resObj.stdout ? `  │  stdout: "${resObj.stdout}"` : ''}`;
            }
          } else if (data.toolName === 'edit_file') {
            displayResult = `${resObj.action} → ${resObj.path}`;
          } else if (data.toolName === 'create_directory') {
            // Wait, create_directory action could be 'created_directory' but the prompt says 'created -> {path}'. Let's hardcode it.
            displayResult = `created → ${resObj.path}`;
          } else if (data.toolName === 'list_files') {
            const count = resObj.files ? resObj.files.length : 0;
            displayResult = `listed ${resObj.path}  (${count} entries)`;
          } else if (data.toolName === 'read_file') {
            const chars = resObj.content ? resObj.content.length : 0;
            displayResult = `read ${resObj.file_path}  (${chars} chars)`;
          }
        } catch (e) { }

        return (
          <Box marginTop={1}>
            {isErr ? (
              <Text backgroundColor="red" color="white" bold> ✘ ERROR </Text>
            ) : (
              <Text backgroundColor="green" color="black" bold> ✔ DONE </Text>
            )}
            <Text>  {displayResult}</Text>
          </Box>
        );
      })()}
    </Box>
  );
};

export const ToolBlock = React.memo(ToolBlockComponent);
