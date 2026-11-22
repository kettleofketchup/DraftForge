// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MAX_SCREENSHOT_BYTES } from '../schemas';
import { ScreenshotInput } from '../ScreenshotInput';

const createObjectURL = vi.fn((file: Blob) => `blob:${(file as File).name}`);
const revokeObjectURL = vi.fn();

beforeEach(() => {
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: revokeObjectURL,
  });
});

afterEach(() => {
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
});

function Harness({ onChange }: { onChange?: (f: File | null) => void }) {
  const [file, setFile] = useState<File | null>(null);
  return (
    <ScreenshotInput
      value={file}
      onChange={(next) => {
        setFile(next);
        onChange?.(next);
      }}
      required
    />
  );
}

function pick(file: File) {
  fireEvent.change(screen.getByTestId('mmr-screenshot-input'), {
    target: { files: [file] },
  });
}

describe('ScreenshotInput', () => {
  it('accepts only png, jpeg and webp', () => {
    render(<Harness />);
    expect(screen.getByTestId('mmr-screenshot-input')).toHaveAttribute(
      'accept',
      'image/png,image/jpeg,image/webp',
    );
  });

  it('rejects a gif with a visible error', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    pick(new File(['x'], 'a.gif', { type: 'image/gif' }));
    expect(screen.getByRole('alert')).toHaveTextContent('PNG, JPEG or WebP');
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId('mmr-screenshot-preview')).toBeNull();
  });

  it('rejects a 9 MB file with a visible error', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const big = new File(['x'], 'big.png', { type: 'image/png' });
    Object.defineProperty(big, 'size', { value: 9 * 1024 * 1024 });
    expect(big.size).toBeGreaterThan(MAX_SCREENSHOT_BYTES);
    pick(big);
    expect(screen.getByRole('alert')).toHaveTextContent('8 MB');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('shows a preview of a valid file', () => {
    render(<Harness />);
    pick(new File(['x'], 'shot.png', { type: 'image/png' }));
    expect(screen.getByTestId('mmr-screenshot-preview')).toHaveAttribute(
      'src',
      'blob:shot.png',
    );
    expect(screen.getByText('shot.png')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('revokes the preview URL on remove', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    pick(new File(['x'], 'shot.png', { type: 'image/png' }));
    fireEvent.click(screen.getByRole('button', { name: /remove/i }));
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:shot.png');
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.queryByTestId('mmr-screenshot-preview')).toBeNull();
  });

  it('revokes the preview URL on unmount', () => {
    const { unmount } = render(<Harness />);
    pick(new File(['x'], 'shot.webp', { type: 'image/webp' }));
    unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:shot.webp');
  });

  it('accepts a dropped file', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const file = new File(['x'], 'drop.jpg', { type: 'image/jpeg' });
    fireEvent.drop(screen.getByTestId('mmr-screenshot-dropzone'), {
      dataTransfer: { files: [file] },
    });
    expect(onChange).toHaveBeenCalledWith(file);
  });

  it('shows an external error', () => {
    render(
      <ScreenshotInput value={null} onChange={vi.fn()} error="too_large" />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('too_large');
  });
});
