import os
import sys
sys.path.append("..")
import argparse
import time
import subprocess

from copy import deepcopy
from src.utils.simulation import SIMU
from src.utils.utils import line_graph
from src.DMP.SIR import DMP_SIR

import pickle as pkl
import networkx as nx
import numpy as np

def cave_index_fun(src_nodes, tar_nodes):
    edge_list = [(int(s), int(t)) for s, t in zip(src_nodes, tar_nodes)]
    E = len(edge_list)
    G = nx.DiGraph()
    G.add_edges_from(edge_list)
    attr = {edge:w for edge, w in zip(edge_list, range(E))}
    nx.set_edge_attributes(G, attr, "idx")

    cave = []
    for edge in edge_list:
        if G.has_edge(*edge[::-1]):
            cave.append(G.edges[edge[::-1]]["idx"])
        else:
            cave.append(E)
    return np.array(cave)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-df", "--diffusion", type=str, default="SIR",
                        help="The diffusion model")
    parser.add_argument("-ns", "--num_samples", type=int, default=100,
                        help="number of samples to be generated")
    parser.add_argument("-ss", "--seed_size", type=float, default=2,
                        help="The maximum percent of nodes been set as nodes")
    args = parser.parse_args()
    print("=== Setting Args ===")
    for arg, value in vars(args).items():
        print("{:>20} : {}".format(arg, value))
     
    data_path = ["../data/er_structure/n{}".format(b) for b in range(10)]
    save_path = [os.path.join(path, "train_data") for path in data_path]
    save_name = "{}_{}.pkl".format(args.diffusion, args.num_samples)

    for dp in data_path:
        if not os.path.exists(dp):
            os.mkdir(dp)
    for sp in save_path:
        if not os.path.exists(sp):
            os.mkdir(sp)
    
    candidatesN = np.linspace(10, 50, 11)
    
    for sp, p in zip(save_path, range(10)):
        dataset = {"config":args,
                "graph":[],
                "seeds": [],
                "node2edge": [],
                "snode2edge":[],
                "tnode2edge":[],
                "edge2tnode":[],
                "nb_matrix":[],
                "node_prob": [],
                "edge_prob":[],
                "node_seed":[],
                "cave_index":[],
                "simu_marginal":[],
                "dmp_marginal":[]}
        n_min, n_max = candidatesN[p], candidatesN[p+1]
        print("nmin = {} nmax = {}".format(n_min, n_max))
        for s in range(args.num_samples):
            t0 = time.time()
            # Random ER graph    
            # 节点数变化 平均度不变 为4左右
            for i in range(100): 
                n = np.random.randint(low=n_min, high=n_max, size=1)[0] 
                graph = nx.random_regular_graph(d=4, n=n)
                if 0 not in list(dict(graph.degree()).values()):
                    break
                else:
                    continue
            node_rename = {n:i for i, n in enumerate(graph.nodes())}
            graph = nx.relabel_nodes(graph, node_rename)
            graph = nx.DiGraph(graph) # Bi directed graph from original undirected graph
            # transformation matrix
            edge_index = np.array(list(graph.edges()))
            N = graph.number_of_nodes()
            E = graph.number_of_edges()
            snode2edge, tnode2edge, edge2tnode, NB_matrix = line_graph(edge_index, N, E)
            row, col = np.array(graph.edges()).T
            cave_index = cave_index_fun(row, col)

            dataset["node2edge"].append(snode2edge)
            dataset["snode2edge"].append(snode2edge)
            dataset["tnode2edge"].append(tnode2edge)
            dataset["edge2tnode"].append(edge2tnode)
            dataset["nb_matrix"].append(NB_matrix)
            dataset["cave_index"].append(cave_index)

            node_prob = np.ones(N) * 0.35
            weight = np.ones(E) * 0.2

            # random seeds size
            if args.seed_size >=1:
                seeds_size = int(args.seed_size)
            else:
                seeds_size = np.random.randint(1, int(args.seed_size*N), 1)
            G = deepcopy(graph)
            # Setting parameters for edges nodes
            weight_map = {e:w for e, w in zip(G.edges, weight)}
            nx.set_edge_attributes(G, weight_map, "weight")

            node_prob_map = {n:p for n, p in zip(G.nodes, node_prob)}
            nx.set_node_attributes(G, node_prob_map, "node_prob")

            # Saving Graph with attributes
            dataset["graph"].append(G)

            # Generate info. for LGNN model
            dataset["node_prob"].append(node_prob[:, None])
            edge_feat = np.array([weight_map[tuple(e)] for e in edge_index])[:, None] # size [2E, 1]
            dataset["edge_prob"].append(edge_feat)

            seeds = np.random.choice(list(G.nodes()), size=seeds_size, replace=False)
            dataset["seeds"].append(seeds)

            # Seeds as feature
            node_seed = np.zeros(N)
            node_seed[seeds] = 1
            dataset["node_seed"].append(node_seed[:, None])

            # Simulation
            simu_marginal = SIMU(args.diffusion, G, seeds, path="../src/utils/")
            dataset["simu_marginal"].append(simu_marginal)

            # DMP
            wadj = nx.adj_matrix(G).toarray()
            dmp_sir = DMP_SIR(weight_adj=wadj, nodes_gamma=node_prob)
            dmp_simulation = dmp_sir.run(list(seeds))
            dataset["dmp_marginal"].append(dmp_simulation)

            print("{:^3} Sample Generated, Time={:.1f}s, Influence={:.1f}/{}".\
                format(s, time.time()-t0, simu_marginal[-1, :, -1].sum(), G.number_of_nodes()))

        # Saving
        with open(os.path.join(sp, save_name), "wb") as f:
            pkl.dump(dataset, f)