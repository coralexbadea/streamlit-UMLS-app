import os
import json
import requests
import networkx as nx
from collections import deque
from langdetect import detect
import plotly.graph_objects as go
import streamlit as st
import io
import zipfile

# Fetch API key from environment variables
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    st.error("API_KEY environment variable not set. Please configure it and restart the application.")
    st.stop()

def get_request(uri):
    search_url = uri + "&apiKey=" + API_KEY
    response = requests.get(search_url)
    if response.status_code == 200:
        return response.json()
    else:
        st.warning(f"Failed to fetch URI: {uri}. Response code: {response.status_code}")
        return None

def find_uri_from_name(term_name):
    query_term_name = "+".join(term_name.split(" "))
    uri = f"https://uts-ws.nlm.nih.gov/rest/search/current?string={query_term_name}"
    search_data = get_request(uri)

    if search_data and search_data.get("result", {}).get("results"):
        resource = search_data["result"]["results"][0]
        return resource['name'], resource["uri"]
    else:
        st.warning(f"Term '{term_name}' not found.")
        return None, None

def get_relations(depth, name, uri, page_number, graph):
    relations_uri = f"{uri}/relations?pageNumber={page_number}"
    json_data = get_request(relations_uri)
    kids = []

    for info in json_data.get("result", []):
        if detect(info.get("relatedIdName")) == 'en': # only add information
            graph.add_edge(
                name,
                info.get("relatedIdName"),
                label=f"{info.get('relationLabel')}({info.get('additionalRelationLabel')})",
                uri=info.get("relatedId"),
                depth=depth
            )

            kids.append((info.get("relatedIdName"), info.get("relatedId")))

    return kids

def create_3d_graph(graph, save_file):
    pos = nx.spring_layout(graph, dim=3, seed=42)  # 3D layout

    x_nodes = [pos[node][0] for node in graph.nodes()]
    y_nodes = [pos[node][1] for node in graph.nodes()]
    z_nodes = [pos[node][2] for node in graph.nodes()]

    node_depth = {}
    for u, v, data in graph.edges(data=True):
        depth = data.get("depth", 0)
        if u not in node_depth:
            node_depth[u] = depth
        if v not in node_depth:
            node_depth[v] = depth

    depth_values = [node_depth.get(node, 0) for node in graph.nodes()]

    edge_x, edge_y, edge_z = [], [], []
    for u, v in graph.edges():
        x0, y0, z0 = pos[u]
        x1, y1, z1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
        edge_z += [z0, z1, None]

    edge_trace = go.Scatter3d(
        x=edge_x, y=edge_y, z=edge_z,
        line=dict(width=0.5, color='gray'),
        hoverinfo='none',
        mode='lines'
    )

    node_trace = go.Scatter3d(
        x=x_nodes, y=y_nodes, z=z_nodes,
        mode='markers',
        hoverinfo='text',
        marker=dict(
            showscale=True,
            colorscale='Viridis',
            size=10,
            color=depth_values,
            colorbar=dict(thickness=15, title="Node Depth", xanchor="left", titleside="right")
        )
    )

    node_trace.text = list(graph.nodes())

    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        title="3D Graph Visualization",
                        showlegend=False,
                        scene=dict(
                            xaxis=dict(showgrid=False, zeroline=False, visible=False),
                            yaxis=dict(showgrid=False, zeroline=False, visible=False),
                            zaxis=dict(showgrid=False, zeroline=False, visible=False),
                        ),
                        hovermode='closest'
                    ))

    if save_file:
        fig.write_html("3d_graph.html")
        st.success("3D graph saved as 3d_graph.html")

    st.plotly_chart(fig, use_container_width=True)


def create_zip():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        with open("relationships.txt", "r") as txt_file:
            zip_file.writestr("relationships.txt", txt_file.read())
        with open("3d_graph.html", "r") as html_file:
            zip_file.writestr("3d_graph.html", html_file.read())
    zip_buffer.seek(0)
    return zip_buffer

def main():
    st.title("3D Graph Visualization of UMLS Relationships")

    term_name = st.text_input("Enter the term to search:", "Age-related macular degeneration")
    max_depth = st.slider("Select max depth for traversal:", min_value=1, max_value=5, value=3)

    if st.button("Generate Graph"):
        st.write("Fetching data... This might take a few moments.")

        name_start, uri_start = find_uri_from_name(term_name)

        if name_start and uri_start:
            frontier = deque([(name_start, uri_start)])
            expanded_uris = []
            graph = nx.DiGraph()
            depth = 0

            while depth <= max_depth:
                for _ in range(len(frontier)):
                    current_node = frontier.popleft()
                    name, uri = current_node[0], current_node[1]
                    entity_id = uri.split('/')[-1]

                    if depth <= max_depth and entity_id not in expanded_uris:
                        frontier.extend(get_relations(depth, name, uri, 1, graph))
                        expanded_uris.append(entity_id)

                depth += 1

            st.write("Graph generation complete.")

            # Display available nodes and their relationships
            st.subheader("Available Nodes and Their Relationships")
            relationships = []
            for u, v, data in graph.edges(data=True):
                relationship = f"{u} --> {v} (Relation: {data['label']})"
                relationships.append(relationship)
            st.text("\n".join(relationships))

            # Save relationships as a TXT file
            relationships_txt = "\n".join(relationships)
            with open("relationships.txt", "w") as txt_file:
                txt_file.write(relationships_txt)

            # Generate the 3D graph and save as HTML
            create_3d_graph(graph, save_file=True)
            
            zip_buffer = create_zip()
            st.download_button(
                label="Download as ZIP",
                data=zip_buffer,
                file_name="files.zip",
                mime="application/zip"
            )

if __name__ == "__main__":
    main()
