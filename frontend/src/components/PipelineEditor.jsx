import React, { useEffect, useState } from 'react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';

function initialStages(pipeline) {
  const stages = Array.isArray(pipeline?.stages) ? pipeline.stages : [];
  if (stages.length) {
    return stages.map((stage, index) => ({
      id: stage?.id || '',
      name: stage?.name || '',
      key: `${stage?.id || 'stage'}-${index}`,
    }));
  }
  return [
    { id: '', name: '', key: 'stage-new-0' },
    { id: '', name: '', key: 'stage-new-1' },
  ];
}

function SortableStageRow({ stage, index, stageCount, dropIndicator, onChange, onRemove }) {
  const {
    attributes,
    isDragging,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ id: stage.key });
  const style = {
    transform: transform
      ? `translate3d(${transform.x}px, ${transform.y}px, 0)`
      : undefined,
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={[
        'client-stage-editor-row',
        isDragging ? 'is-dragging' : '',
        dropIndicator ? `drop-${dropIndicator}` : '',
      ].filter(Boolean).join(' ')}
    >
      <button
        type="button"
        className="client-stage-editor-drag-handle"
        {...attributes}
        {...listeners}
        aria-label={`Reorder stage ${index + 1}`}
      >
        <i className="fas fa-grip-vertical" aria-hidden="true"></i>
      </button>
      <span className="client-hiring-stage-number">{index + 1}</span>
      <input
        value={stage.name}
        onChange={(event) => onChange(stage.key, event.target.value)}
        aria-label={`Stage ${index + 1}`}
        required
      />
      <div className="client-stage-editor-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => onRemove(stage.key)}
          disabled={stageCount <= 2}
          aria-label={`Remove stage ${index + 1}`}
        >
          <i className="fas fa-times"></i>
        </button>
      </div>
    </div>
  );
}

function PipelineEditor({ pipeline = null, saving = false, onSave, onCancel }) {
  const [name, setName] = useState(pipeline?.name || '');
  const [stages, setStages] = useState(() => initialStages(pipeline));
  const [activeId, setActiveId] = useState(null);
  const [overId, setOverId] = useState(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  useEffect(() => {
    setName(pipeline?.name || '');
    setStages(initialStages(pipeline));
  }, [pipeline]);

  const updateStage = (key, value) => {
    setStages((current) => current.map((stage, stageIndex) => (
      stage.key === key ? { ...stage, name: value } : stage
    )));
  };

  const removeStage = (key) => {
    setStages((current) => (
      current.length > 2 ? current.filter((stage) => stage.key !== key) : current
    ));
  };

  const handleDragEnd = ({ active, over }) => {
    setActiveId(null);
    setOverId(null);
    if (!over || active.id === over.id) return;

    setStages((current) => {
      const fromIndex = current.findIndex((stage) => stage.key === active.id);
      const toIndex = current.findIndex((stage) => stage.key === over.id);
      return fromIndex < 0 || toIndex < 0 ? current : arrayMove(current, fromIndex, toIndex);
    });
  };

  const activeIndex = stages.findIndex((stage) => stage.key === activeId);
  const overIndex = stages.findIndex((stage) => stage.key === overId);

  const addStage = () => {
    setStages((current) => [
      ...current,
      { id: '', name: '', key: `stage-new-${Date.now()}-${current.length}` },
    ]);
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    onSave({
      name: name.trim(),
      stages: stages.map((stage, order) => ({
        ...(stage.id ? { id: stage.id } : {}),
        name: stage.name,
        order,
      })),
    });
  };

  return (
    <form className="client-config-editor" onSubmit={handleSubmit}>
      <label className="jd-create-label-color client-pipeline-name-field">
        <span>Pipeline name</span>
        <input value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <div className="client-editor-heading">
        <strong>Hiring stages</strong>
        <span>{stages.length} stages</span>
      </div>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={({ active }) => {
          setActiveId(active.id);
          setOverId(active.id);
        }}
        onDragOver={({ over }) => setOverId(over?.id ?? null)}
        onDragCancel={() => {
          setActiveId(null);
          setOverId(null);
        }}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={stages.map((stage) => stage.key)}
          strategy={verticalListSortingStrategy}
        >
          <div className="client-stage-editor-grid">
            {stages.map((stage, index) => {
              const dropIndicator = index === overIndex && activeIndex !== overIndex
                ? (activeIndex < overIndex ? 'after' : 'before')
                : null;

              return (
                <SortableStageRow
                  key={stage.key}
                  stage={stage}
                  index={index}
                  stageCount={stages.length}
                  dropIndicator={dropIndicator}
                  onChange={updateStage}
                  onRemove={removeStage}
                />
              );
            })}
          </div>
        </SortableContext>
      </DndContext>
      <button type="button" className="client-hiring-stage-add" onClick={addStage}>
        <i className="fas fa-plus"></i> Add stage
      </button>
      <p className="client-editor-note">Changes apply to new jobs only.</p>
      <div className="client-editor-footer">
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={saving}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </form>
  );
}

export default PipelineEditor;
