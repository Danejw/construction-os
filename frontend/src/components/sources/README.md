# Sources Components

The `AddSourceDialog` accepts file uploads only (drag-and-drop or click-to-browse) and starts processing immediately with defaults.

## Usage

### Basic Usage

```tsx
import { AddSourceDialog } from '@/components/sources/AddSourceDialog'

<AddSourceDialog open={open} onOpenChange={setOpen} />
```

### With Default Project

```tsx
<AddSourceDialog
  open={open}
  onOpenChange={setOpen}
  defaultprojectId="project:123"
/>
```

### Via Create Dialogs Provider

```tsx
const { openSourceDialog } = useCreateDialogs()
openSourceDialog()
```

## Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `open` | `boolean` | - | Dialog open state |
| `onOpenChange` | `(open: boolean) => void` | - | Open state callback |
| `defaultprojectId` | `string` | - | Attach uploaded sources to this project |

## Related Hooks

- `useCreateSource()` - Submits source creation
