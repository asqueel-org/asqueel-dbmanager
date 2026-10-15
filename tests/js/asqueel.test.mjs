import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../../src/asqueel_dbmanager/pages/asqueel.js', import.meta.url), 'utf8');
const {comparisonTrees} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('JSON comparison aligns absent and changed nodes on both sides', () => {
    const [a, b] = comparisonTrees({table: {id: 1, title: null}}, {table: {id: 2, extra: false}});
    assert.equal(a.status, 'changed');
    assert.deepEqual(a.children[0].children.map(n => [n.name, n.status]), [
        ['extra', 'current'], ['id', 'changed'], ['title', 'desired']]);
    assert.deepEqual(a.children[0].children.map(n => n.path), b.children[0].children.map(n => n.path));
    assert.equal(a.children[0].children[0].missing, true);
    assert.equal(b.children[0].children[2].missing, true);
    assert.equal(a.children[0].children[2].detail.value, null);
});

test('Order does not create differences, but arrays and objects differ', () => {
    assert.equal(comparisonTrees({a: 1, b: 2}, {b: 2, a: 1})[0].status, 'equal');
    assert.equal(comparisonTrees([], {})[0].status, 'changed');
    assert.equal(comparisonTrees({a: [1]}, {a: [1]})[0].status, 'equal');
});

test('Literal dots and HTML in names are preserved as path segments', () => {
    const [a] = comparisonTrees({'a.b': {'<script>': '<img>'}}, {});
    assert.deepEqual(a.children[0].children[0].path, ['a.b', '<script>']);
    assert.equal(a.children[0].children[0].detail.value, '<img>');
});
