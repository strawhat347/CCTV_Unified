import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet-draw';

window.L = L;

export default function DrawControl({ onChange, clearTrigger }) {
  const map = useMap();
  const drawnItemsRef = useRef(null);
  
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!drawnItemsRef.current) {
      drawnItemsRef.current = new L.FeatureGroup();
    }
    const drawnItems = drawnItemsRef.current;
    
    if (!map.hasLayer(drawnItems)) {
      map.addLayer(drawnItems);
    }

    const drawControl = new L.Control.Draw({
      position: 'topright',
      edit: {
        featureGroup: drawnItems
      },
      draw: {
        polyline: false,
        circle: false,
        circlemarker: false,
        marker: false,
        rectangle: false,
        polygon: {
          maxPoints: 8
        },
      }
    });

    map.addControl(drawControl);

    const handleCreated = (e) => {
      drawnItems.clearLayers(); // Only keep one geofence at a time
      const layer = e.layer;
      drawnItems.addLayer(layer);
      
      // Fire whenever vertices are dragged
      layer.on('edit', () => {
        if (onChangeRef.current) onChangeRef.current(layer);
      });

      // Automatically enter edit mode after drawing finishes
      if (layer.editing) {
        layer.editing.enable();
      }

      if (onChangeRef.current) {
        onChangeRef.current(layer);
      }
    };

    map.on(L.Draw.Event.CREATED, handleCreated);

    return () => {
      map.off(L.Draw.Event.CREATED, handleCreated);
      map.removeControl(drawControl);
      map.removeLayer(drawnItems);
    };
  }, [map]);

  useEffect(() => {
    if (drawnItemsRef.current) {
      drawnItemsRef.current.clearLayers();
    }
  }, [clearTrigger]);

  return null;
}
