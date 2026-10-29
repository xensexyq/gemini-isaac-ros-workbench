#!/usr/bin/env python3
"""Rebuild a stopped session from saved keyframes and optimized pose history."""
import argparse
from pathlib import Path
import json
import numpy as np
from global_mapping import GlobalMap


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path,help='Session global/ directory')
    args=parser.parse_args()
    folder=args.directory.resolve()
    folder.relative_to(Path(__file__).resolve().parents[1]/'runs')
    mapping=GlobalMap(folder)
    state=json.loads((folder/'global-state.json').read_text())
    mapping.optimized={int(k):np.asarray(v) for k,v in state['optimized_poses'].items()}
    mapping.revision=state['revision']
    for filename in state['keyframes']:
        path=folder/filename
        if path.parent!=folder or not filename.startswith('keyframe-') or path.suffix!='.npz':
            raise ValueError('Invalid keyframe filename')
        with np.load(path,allow_pickle=False) as data:
            frame={k:data[k] for k in ('points','colors','faces','relative')}
            frame.update(stamp=int(data['stamp']),anchor=int(data['anchor']))
        mapping.frames.append(frame)
    mapping.status['keyframes']=len(mapping.frames)
    mapping.dirty=True;mapping.export()
    print(json.dumps(mapping.status))


if __name__=='__main__': main()
