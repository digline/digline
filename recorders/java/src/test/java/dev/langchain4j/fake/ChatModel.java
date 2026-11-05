package dev.langchain4j.fake;

import com.anthropic.client.AnthropicClient;
import com.anthropic.models.messages.MessageCreateParams;

/**
 * A frame of LangChain4j's package between the application and the SDK, as
 * a chat model built on a provider's client puts one: the call is made here,
 * not in the application's code. Not LangChain4j; only its package.
 */
public final class ChatModel {

    private final AnthropicClient client;

    public ChatModel(AnthropicClient client) {
        this.client = client;
    }

    public void chat(MessageCreateParams asked) {
        client.messages().create(asked);
    }
}
