import { JsonTreeView } from './JsonTreeView';

export function JsonView({ value }: { value: unknown }) {
  return (
    <div className="json-view custom-scroll">
      <JsonTreeView value={value} />
    </div>
  );
}
