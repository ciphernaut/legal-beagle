import { ApiError, getFrameworks, getNode, getTree } from "./client";
import { stubFetch } from "../test/fetchMock";
import { nodeFixture, treeFixture } from "../test/fixtures";

test("getTree hits /api/tree?root=… and returns the tree", async () => {
  const mock = stubFetch({ "GET /api/tree?root=constitution": { body: treeFixture } });
  const tree = await getTree("constitution");
  expect(tree.node.label).toMatch(/Constitution/);
  expect(mock).toHaveBeenCalledTimes(1);
});

test("getNode encodes type and id in the path", async () => {
  stubFetch({ "GET /api/nodes/case/100": { body: nodeFixture } });
  const node = await getNode("case", 100);
  expect(node.neighbours).toHaveLength(2);
});

test("getFrameworks returns the list", async () => {
  stubFetch({ "GET /api/reason/frameworks": { body: ["common_law"] } });
  expect(await getFrameworks()).toEqual(["common_law"]);
});

test("non-2xx raises ApiError with the status", async () => {
  stubFetch({ "GET /api/nodes/case/999": { status: 404, body: { detail: "node not found" } } });
  await expect(getNode("case", 999)).rejects.toMatchObject({ status: 404 });
  await expect(getNode("case", 999)).rejects.toBeInstanceOf(ApiError);
});
